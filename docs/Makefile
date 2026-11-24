PANDOC ?= pandoc
PREFIX ?= /usr/local
BUILD_DIR ?= build/man
MAN1_DIR ?= $(DESTDIR)$(PREFIX)/share/man/man1
MAN7_DIR ?= $(DESTDIR)$(PREFIX)/share/man/man7

PANDOC_FLAGS := --standalone --from=gfm+yaml_metadata_block --to=man \
  --lua-filter=man-filter.lua

MAN1_SOURCES := CLI_REFERENCE.md
MAN7_SOURCES := \
  ADDING_A_JETSON_ORIN.md \
  ADDING_A_NEW_NODE.md \
  ARGO_CLUSTER_ADMINS.md \
  DEPLOYING_ARGO_WORKFLOW.md \
  SETUP.md \
  SETUP_USERS.md \
  TUNNELING.md
MAN_SOURCES := $(MAN1_SOURCES) $(MAN7_SOURCES)

MAN1_PAGES := $(BUILD_DIR)/jihwija.1
MAN7_PAGES := \
  $(BUILD_DIR)/jihwija-add-jetson.7 \
  $(BUILD_DIR)/jihwija-add-node.7 \
  $(BUILD_DIR)/jihwija-argo-template-admin.7 \
  $(BUILD_DIR)/jihwija-argo-workflow.7 \
  $(BUILD_DIR)/jihwija-setup.7 \
  $(BUILD_DIR)/jihwija-users.7 \
  $(BUILD_DIR)/jihwija-tunneling.7
MAN_PAGES := $(MAN1_PAGES) $(MAN7_PAGES)

UNREGISTERED_SOURCES := $(filter-out $(MAN_SOURCES),$(wildcard *.md))
MISSING_SOURCES := $(filter-out $(wildcard *.md),$(MAN_SOURCES))
ifneq ($(strip $(UNREGISTERED_SOURCES)),)
$(error Register these Markdown files in docs/Makefile: $(UNREGISTERED_SOURCES))
endif
ifneq ($(strip $(MISSING_SOURCES)),)
$(error Registered Markdown files do not exist: $(MISSING_SOURCES))
endif

.PHONY: all man check install-man clean

all: man

man: $(MAN_PAGES)

$(BUILD_DIR):
	mkdir -p $@

define build_man_page
$(BUILD_DIR)/$(1).$(2): $(3) man-filter.lua | $(BUILD_DIR)
	$(PANDOC) $(PANDOC_FLAGS) --output=$$@ $$<
endef

$(eval $(call build_man_page,jihwija,1,CLI_REFERENCE.md))
$(eval $(call build_man_page,jihwija-add-jetson,7,ADDING_A_JETSON_ORIN.md))
$(eval $(call build_man_page,jihwija-add-node,7,ADDING_A_NEW_NODE.md))
$(eval $(call build_man_page,jihwija-argo-template-admin,7,ARGO_CLUSTER_ADMINS.md))
$(eval $(call build_man_page,jihwija-argo-workflow,7,DEPLOYING_ARGO_WORKFLOW.md))
$(eval $(call build_man_page,jihwija-setup,7,SETUP.md))
$(eval $(call build_man_page,jihwija-users,7,SETUP_USERS.md))
$(eval $(call build_man_page,jihwija-tunneling,7,TUNNELING.md))

check: man
	@if command -v groff >/dev/null 2>&1; then \
		for page in $(MAN_PAGES); do \
			groff -t -man -Tutf8 "$$page" >/dev/null 2>&1; \
		done; \
	fi

install-man: man
	install -d "$(MAN1_DIR)" "$(MAN7_DIR)"
	install -m 0644 $(MAN1_PAGES) "$(MAN1_DIR)/"
	install -m 0644 $(MAN7_PAGES) "$(MAN7_DIR)/"

clean:
	$(RM) -r build
