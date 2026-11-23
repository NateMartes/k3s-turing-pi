from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from jihwija.cli import ROUTES, format_help, resolve_route, route_scripts


ROOT = Path(__file__).resolve().parents[1]
PLUMBING = ROOT / "scripts" / "plumbing-scripts"
LIB = PLUMBING / "lib"
lib_spec = importlib.util.spec_from_file_location(
    "jihwija_plumbing_lib",
    LIB / "__init__.py",
    submodule_search_locations=[str(LIB)],
)
assert lib_spec and lib_spec.loader
lib_package = importlib.util.module_from_spec(lib_spec)
sys.modules[lib_spec.name] = lib_package
lib_spec.loader.exec_module(lib_package)

jihwija_common = importlib.import_module("jihwija_plumbing_lib.jihwija_common")
k3s_gpu_taints = importlib.import_module("jihwija_plumbing_lib.k3s_gpu_taints")
JihwijaError = jihwija_common.JihwijaError
add_host = jihwija_common.add_host
inventory_hosts = jihwija_common.inventory_hosts
parse_env = jihwija_common.parse_env
remove_host = jihwija_common.remove_host
validate_networks = jihwija_common.validate_networks
write_env = jihwija_common.write_env
gpu_node_names = k3s_gpu_taints.gpu_node_names


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {
            "all": {
                "vars": {"ansible_user": "operator"},
                "children": {
                    "workers": {
                        "hosts": {
                            "worker-1": {"ansible_host": "10.42.0.10"}
                        }
                    }
                },
            }
        }
        self.settings = {
            "k3s_lan_cidr": "10.42.0.0/24",
            "k3s_cluster_cidr": "10.244.0.0/16",
            "k3s_service_cidr": "10.43.0.0/16",
        }

    def test_add_and_remove_host_preserves_group(self):
        add_host(
            self.inventory,
            "workers",
            "worker-2",
            {"ansible_host": "10.42.0.11", "is_desktop_node": True},
        )
        self.assertIn("worker-2", inventory_hosts(self.inventory))
        self.assertTrue(remove_host(self.inventory, "worker-2"))
        self.assertIn("workers", self.inventory["all"]["children"])

    def test_new_group_and_network_validation(self):
        add_host(self.inventory, "gpu_nodes", "gpu-1", {"ansible_host": "10.42.0.20"})
        validate_networks(self.settings, inventory_hosts(self.inventory))

    def test_duplicate_addresses_are_rejected(self):
        add_host(self.inventory, "workers", "worker-2", {"ansible_host": "10.42.0.10"})
        with self.assertRaises(JihwijaError):
            validate_networks(self.settings, inventory_hosts(self.inventory))

    def test_overlapping_networks_are_rejected(self):
        self.settings["k3s_cluster_cidr"] = "10.42.0.0/16"
        with self.assertRaises(JihwijaError):
            validate_networks(self.settings, inventory_hosts(self.inventory))


class EnvironmentTests(unittest.TestCase):
    def test_environment_round_trip_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jihwija.env"
            values = {"HARBOR_ADMIN_PASSWORD": "A value with 'quotes'", "ARGO_HOSTNAME": "argo.example.test"}
            write_env(values, path)
            self.assertEqual(parse_env(path), values)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class InstallerTests(unittest.TestCase):
    def test_failed_install_restores_previous_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_root = root / "opt" / "jihwija"
            install_root.mkdir(parents=True)
            marker = install_root / "previous-release"
            marker.write_text("preserve me\n")

            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_id = fake_bin / "id"
            fake_id.write_text("#!/bin/sh\necho 0\n")
            fake_id.chmod(0o755)
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                "venv=$3\n"
                "mkdir -p \"$venv/bin\"\n"
                "printf '#!/bin/sh\\nexit 42\\n' > \"$venv/bin/pip\"\n"
                "chmod +x \"$venv/bin/pip\"\n"
            )
            fake_python.chmod(0o755)

            env = os.environ.copy()
            env.update(
                JIHWIJA_INSTALL_ROOT=str(install_root),
                JIHWIJA_LINK_PATH=str(root / "bin-links" / "jihwija"),
                JIHWIJA_PROFILE_DIR=str(root / "profiles"),
                JIHWIJA_SKIP_PACKAGES="1",
                PATH=f"{fake_bin}:{env['PATH']}",
            )
            result = subprocess.run(
                [str(ROOT / "install.sh")],
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), "preserve me\n")
            self.assertFalse((install_root / "pyproject.toml").exists())
            self.assertIn("restoring the previous", result.stderr)


class UserRemovalTests(unittest.TestCase):
    def test_failed_component_is_retained_and_linux_user_is_preserved(self):
        sys.modules["lib"] = lib_package
        module = runpy.run_path(str(PLUMBING / "remove-user"))
        main = module["main"]
        namespace = main.__globals__
        state = {
            "services": ["portainer", "rancher"],
            "linux_user_created": True,
            "home": "/nonexistent/jihwija-test-user",
            "portainer_host": "portainer.example.test",
            "rancher_host": "rancher.example.test",
        }
        saved = []
        namespace.update(
            require_root=lambda: None,
            validate_username=lambda value: value,
            load_state=lambda _username: state,
            user_exists=lambda _username: True,
            require_hostname=lambda value, *_args: value,
            print_unverified_https_notice=lambda _services: None,
            run_plumbing=lambda name, *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0 if name == "uninstall-portainer-account" else 1
            ),
            save_state=lambda _username, value: saved.append({
                **value,
                "services": list(value.get("services", [])),
            }),
            state_path=lambda username: Path("/state") / f"{username}.json",
            run=lambda *_args, **_kwargs: self.fail("Linux removal must not run"),
        )
        original_argv = sys.argv
        sys.argv = [
            "remove-user", "alice", "--only", "portainer,rancher",
            "--no-purge-data", "--yes",
        ]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main()
        finally:
            sys.argv = original_argv

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(saved[-1]["services"], ["rancher"])
        self.assertFalse(saved[-1]["portainer_account"])
        self.assertTrue(saved[-1]["linux_user"])


class RepositoryTests(unittest.TestCase):
    def test_all_public_routes_have_executable_plumbing(self):
        for script in route_scripts():
            path = PLUMBING / script
            self.assertTrue(path.is_file(), path)
            self.assertTrue(path.stat().st_mode & 0o111, path)

        self.assertEqual(ROUTES["enable"]["quotas"], "enable-quotas")
        self.assertEqual(ROUTES["disable"]["quotas"], "disable-quotas")
        self.assertEqual(ROUTES["trust"]["certs"], "trust-k3s-certs")
        self.assertEqual(
            resolve_route(["set", "user", "quota", "alice"]),
            ("change-user-quota", 3),
        )
        self.assertEqual(resolve_route(["deploy", "--redeploy"]), ("deploy-services", 1))
        self.assertEqual(resolve_route(["trust", "certs"]), ("trust-k3s-certs", 2))
        self.assertIsNone(resolve_route(["set", "user"]))
        self.assertIsNone(resolve_route(["add", "unknown"]))
        self.assertIn("k3s", format_help("install"))
        self.assertIn("secret", format_help("set"))
        self.assertIn("quota", format_help("set user"))
        self.assertIn("node", format_help("add"))
        self.assertIn("certs", format_help("trust"))

    def test_python_modules_live_in_lib(self):
        self.assertEqual(list(PLUMBING.glob("*.py")), [])
        self.assertTrue((LIB / "jihwija_common.py").is_file())
        for path in PLUMBING.iterdir():
            if path.is_file() and path.stat().st_mode & 0o111:
                self.assertNotIn("sys.path.insert", path.read_text(), path)

    def test_service_manifests_parse(self):
        for path in (ROOT / "jihwija-services").glob("*.yaml"):
            list(yaml.safe_load_all(path.read_text()))

    def test_k3s_install_reconciles_gpu_support(self):
        install = (PLUMBING / "install-k3s").read_text()
        add_node = (PLUMBING / "add-node").read_text()
        deploy = (PLUMBING / "deploy-services").read_text()
        self.assertIn('run_plumbing("deploy-services", "--service", "nvidia"', install)
        self.assertIn('run_plumbing("deploy-services", "--service", "nvidia"', add_node)
        self.assertIn('"k3s-taint-gpu-nodes"', deploy)


class GpuTaintTests(unittest.TestCase):
    def test_gpu_label_is_enough_to_identify_node(self):
        original = k3s_gpu_taints.nodes
        k3s_gpu_taints.nodes = lambda: [{
            "metadata": {"name": "jetson-1", "labels": {"nvidia.com/gpu.present": "true"}},
            "status": {"allocatable": {}},
        }]
        try:
            self.assertEqual(gpu_node_names(), ["jetson-1"])
        finally:
            k3s_gpu_taints.nodes = original

    def test_bak_ascii_is_present(self):
        self.assertTrue(hasattr(jihwija_common, "BAK_ASCII") or hasattr(jihwija_common, "JIHWIJA_ASCII"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            jihwija_common.print_bak()
        self.assertIn("Jihwija", buffer.getvalue())

    def test_removed_identifier_is_absent(self):
        removed = "sys" + "admin"
        matches = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix in {".png", ".drawio", ".pyc"}:
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            if removed.lower() in text.lower():
                matches.append(str(path.relative_to(ROOT)))
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
