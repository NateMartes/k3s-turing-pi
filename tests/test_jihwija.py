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
from unittest import mock

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
user_privileges = importlib.import_module("jihwija_plumbing_lib.user_privileges")
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
                "cat > \"$venv/bin/pip\" <<'EOF'\n"
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$JIHWIJA_TEST_PIP_LOG\"\n"
                "case \" $* \" in\n"
                "  *\" setuptools>=68 \"*) exit 0 ;;\n"
                "  *) exit 42 ;;\n"
                "esac\n"
                "EOF\n"
                "chmod +x \"$venv/bin/pip\"\n"
            )
            fake_python.chmod(0o755)
            pip_log = root / "pip.log"

            env = os.environ.copy()
            env.update(
                JIHWIJA_INSTALL_ROOT=str(install_root),
                JIHWIJA_LINK_PATH=str(root / "bin-links" / "jihwija"),
                JIHWIJA_PROFILE_DIR=str(root / "profiles"),
                JIHWIJA_SKIP_PACKAGES="1",
                JIHWIJA_TEST_PIP_LOG=str(pip_log),
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
            pip_calls = pip_log.read_text().splitlines()
            self.assertIn("setuptools>=68", pip_calls[0])
            self.assertIn("--no-build-isolation -e", pip_calls[1])


class UserRemovalTests(unittest.TestCase):
    def test_failed_component_is_retained_and_linux_user_is_preserved(self):
        sys.modules["lib"] = lib_package
        module = runpy.run_path(str(PLUMBING / "remove-user.py"))
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
                [], 0 if name == "uninstall-portainer-account.py" else 1
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
            "remove-user.py", "alice", "--only", "portainer,rancher",
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

    def test_final_user_removal_stops_when_privilege_cleanup_fails(self):
        sys.modules["lib"] = lib_package
        module = runpy.run_path(str(PLUMBING / "remove-user.py"))
        main = module["main"]
        namespace = main.__globals__
        state = {
            "services": ["harbor"],
            "linux_user_created": True,
            "home": "/nonexistent/jihwija-test-user",
            "harbor_host": "harbor.example.test",
            "harbor_account": True,
        }
        saved = []
        removed_state = []
        plumbing_calls = []

        def run_plumbing(name, *_args, **_kwargs):
            plumbing_calls.append(name)
            return subprocess.CompletedProcess(
                [], 1 if name == "revoke-user-privilege.py" else 0
            )

        namespace.update(
            require_root=lambda: None,
            validate_username=lambda value: value,
            load_state=lambda _username: state,
            user_exists=lambda _username: True,
            require_hostname=lambda value, *_args: value,
            print_unverified_https_notice=lambda _services: None,
            run_plumbing=run_plumbing,
            save_state=lambda _username, value: saved.append(dict(value)),
            state_path=lambda username: Path("/state") / f"{username}.json",
            remove_state=lambda username: removed_state.append(username),
            run=lambda *_args, **_kwargs: self.fail(
                "Linux account removal must wait for privilege cleanup"
            ),
        )
        original_argv = sys.argv
        sys.argv = [
            "remove-user.py", "alice", "--only", "harbor",
            "--no-purge-data", "--yes",
        ]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main()
        finally:
            sys.argv = original_argv

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(
            plumbing_calls,
            ["uninstall-harbor-account.py", "revoke-user-privilege.py"],
        )
        self.assertEqual(saved[-1]["services"], [])
        self.assertEqual(removed_state, [])


class UserPrivilegeTests(unittest.TestCase):
    def test_grant_validates_identity_and_applies_repeatable_manifest(self):
        calls = []

        def fake_kubectl(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(user_privileges, "kubectl", fake_kubectl):
            user_privileges.grant_privilege("alice", "argo-template-admin")
            user_privileges.grant_privilege("alice", "argo-template-admin")

        apply_calls = [call for call in calls if call[0][:2] == ["apply", "-f"]]
        self.assertEqual(len(apply_calls), 2)
        self.assertEqual(
            apply_calls[0][1]["input_data"],
            apply_calls[1][1]["input_data"],
        )
        documents = list(yaml.safe_load_all(apply_calls[0][1]["input_data"]))
        self.assertEqual(documents[0]["kind"], "ClusterRole")
        self.assertEqual(
            documents[0]["rules"][0]["resources"],
            ["clusterworkflowtemplates"],
        )
        self.assertEqual(
            set(documents[0]["rules"][0]["verbs"]),
            {"get", "list", "watch", "create", "update", "patch", "delete"},
        )
        self.assertEqual(
            documents[1]["subjects"],
            [{
                "kind": "ServiceAccount",
                "name": "alice-user",
                "namespace": "alice-namespace",
            }],
        )

    def test_grant_rejects_missing_namespace_before_apply(self):
        calls = []

        def fake_kubectl(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, "", "not found")

        with mock.patch.object(user_privileges, "kubectl", fake_kubectl):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    user_privileges.grant_privilege(
                        "alice", "argo-template-admin"
                    )

        self.assertEqual(calls, [["get", "namespace", "alice-namespace"]])

    def test_grant_rejects_missing_service_account_before_apply(self):
        calls = []

        def fake_kubectl(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(
                args,
                0 if args[:2] == ["get", "namespace"] else 1,
                "",
                "not found",
            )

        with mock.patch.object(user_privileges, "kubectl", fake_kubectl):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    user_privileges.grant_privilege(
                        "alice", "argo-template-admin"
                    )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2], "alice-user")
        self.assertNotIn(["apply", "-f", "-"], calls)

    def test_revoke_is_idempotent_and_does_not_require_user_resources(self):
        calls = []

        def fake_kubectl(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(user_privileges, "kubectl", fake_kubectl):
            user_privileges.revoke_privilege("departed-user", "argo-template-admin")
            user_privileges.revoke_privilege("departed-user", "argo-template-admin")

        expected = [
            "delete",
            "clusterrolebinding",
            "departed-user-argo-cluster-workflow-template-admin",
            "--ignore-not-found=true",
        ]
        self.assertEqual(calls, [expected, expected])

    def test_unknown_privilege_is_rejected_by_plumbing_interface(self):
        result = subprocess.run(
            [str(PLUMBING / "grant-user-privilege.py"), "alice", "unknown-role"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertIn("argo-template-admin", result.stderr)

    def test_argo_runner_uninstall_revokes_admin_binding(self):
        sys.modules["lib"] = lib_package
        module = runpy.run_path(str(PLUMBING / "uninstall-argo-workflow-runner.py"))
        main = module["main"]
        namespace = main.__globals__
        revoked = []
        kubectl_calls = []
        namespace.update(
            require_root=lambda: None,
            determine_username=lambda value: value,
            revoke_privilege=lambda username, privilege: revoked.append(
                (username, privilege)
            ),
            kubectl=lambda args: kubectl_calls.append(args),
        )
        original_argv = sys.argv
        sys.argv = [
            "uninstall-argo-workflow-runner.py",
            "--username", "alice",
            "--namespace", "alice-namespace",
        ]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                main()
        finally:
            sys.argv = original_argv

        self.assertEqual(revoked, [("alice", "argo-template-admin")])
        flattened = [item for call in kubectl_calls for item in call]
        self.assertNotIn("argo-cluster-workflow-template-admin", flattened)


class RepositoryTests(unittest.TestCase):
    def test_all_public_routes_have_executable_plumbing(self):
        for script in route_scripts():
            path = PLUMBING / script
            self.assertTrue(path.is_file(), path)
            self.assertTrue(path.stat().st_mode & 0o111, path)

        self.assertEqual(ROUTES["enable"]["quotas"], "enable-quotas.py")
        self.assertEqual(ROUTES["disable"]["quotas"], "disable-quotas.py")
        self.assertEqual(ROUTES["trust"]["certs"], "trust-k3s-certs.py")
        self.assertEqual(ROUTES["grant"]["user"], "grant-user-privilege.py")
        self.assertEqual(ROUTES["revoke"]["user"], "revoke-user-privilege.py")
        self.assertEqual(
            resolve_route(["set", "user", "quota", "alice"]),
            ("change-user-quota.py", 3),
        )
        self.assertEqual(resolve_route(["deploy", "--redeploy"]), ("deploy-services.py", 1))
        self.assertEqual(resolve_route(["trust", "certs"]), ("trust-k3s-certs.py", 2))
        self.assertEqual(
            resolve_route(["grant", "user", "alice", "argo-template-admin"]),
            ("grant-user-privilege.py", 2),
        )
        self.assertEqual(
            resolve_route(["revoke", "user", "alice", "argo-template-admin"]),
            ("revoke-user-privilege.py", 2),
        )
        self.assertIsNone(resolve_route(["set", "user"]))
        self.assertIsNone(resolve_route(["add", "unknown"]))
        self.assertIn("k3s", format_help("install"))
        self.assertIn("secret", format_help("set"))
        self.assertIn("quota", format_help("set user"))
        self.assertIn("node", format_help("add"))
        self.assertIn("certs", format_help("trust"))
        self.assertIn("USERNAME PRIVILEGE", format_help("grant"))
        self.assertIn("USERNAME PRIVILEGE", format_help("revoke"))

    def test_all_plumbing_commands_use_py_extension(self):
        self.assertTrue((LIB / "jihwija_common.py").is_file())
        commands = []
        for path in PLUMBING.iterdir():
            if path.is_file() and path.stat().st_mode & 0o111:
                commands.append(path)
                self.assertEqual(path.suffix, ".py", path)
                self.assertNotIn("sys.path.insert", path.read_text(), path)
        self.assertTrue(commands)

    def test_cli_executes_python_plumbing_with_shared_lib_available(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jihwija.cli",
                "grant",
                "user",
                "--help",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("jihwija grant user", result.stdout)
        self.assertIn("argo-template-admin", result.stdout)

    def test_service_manifests_parse(self):
        for path in (ROOT / "jihwija-services").glob("*.yaml"):
            list(yaml.safe_load_all(path.read_text()))

    def test_k3s_install_reconciles_gpu_support(self):
        install = (PLUMBING / "install-k3s.py").read_text()
        add_node = (PLUMBING / "add-node.py").read_text()
        deploy = (PLUMBING / "deploy-services.py").read_text()
        self.assertIn('run_plumbing("deploy-services.py", "--service", "nvidia"', install)
        self.assertIn('run_plumbing("deploy-services.py", "--service", "nvidia"', add_node)
        self.assertIn('"k3s-taint-gpu-nodes.py"', deploy)


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
