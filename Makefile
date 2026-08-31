ifeq ($(OS),Windows_NT)
$(error Windows is not supported)
endif

LANGUAGE_NAME := tree-sitter-nix
HOMEPAGE_URL := https://github.com/numtide/tree-sitter-nix
# keep in sync with package.json, CMakeLists.txt, Cargo.toml, pyproject.toml, tree-sitter.json
VERSION := 0.5.0
DESCRIPTION := Nix grammar for tree-sitter

# repository
SRC_DIR := src

TS ?= tree-sitter

# install directory layout
PREFIX ?= /usr/local
DATADIR ?= $(PREFIX)/share
INCLUDEDIR ?= $(PREFIX)/include
LIBDIR ?= $(PREFIX)/lib
PCLIBDIR ?= $(LIBDIR)/pkgconfig

# source/object files
PARSER := $(SRC_DIR)/parser.c
EXTRAS := $(filter-out $(PARSER),$(wildcard $(SRC_DIR)/*.c))
OBJS := $(patsubst %.c,%.o,$(PARSER) $(EXTRAS))

# flags
ARFLAGS ?= rcs
override CFLAGS += -I$(SRC_DIR) -std=c11 -fPIC

# ABI versioning
SONAME_MAJOR = $(shell sed -n 's/\#define LANGUAGE_VERSION //p' $(PARSER))
SONAME_MINOR = $(word 1,$(subst ., ,$(VERSION)))

# OS-specific bits
ifeq ($(shell uname),Darwin)
	SOEXT = dylib
	SOEXTVER_MAJOR = $(SONAME_MAJOR).$(SOEXT)
	SOEXTVER = $(SONAME_MAJOR).$(SONAME_MINOR).$(SOEXT)
	LINKSHARED = -dynamiclib -Wl,-install_name,$(LIBDIR)/lib$(LANGUAGE_NAME).$(SOEXTVER),-rpath,@executable_path/../Frameworks
else
	SOEXT = so
	SOEXTVER_MAJOR = $(SOEXT).$(SONAME_MAJOR)
	SOEXTVER = $(SOEXT).$(SONAME_MAJOR).$(SONAME_MINOR)
	LINKSHARED = -shared -Wl,-soname,lib$(LANGUAGE_NAME).$(SOEXTVER)
endif
ifneq ($(filter $(shell uname),FreeBSD NetBSD DragonFly),)
	PCLIBDIR := $(PREFIX)/libdata/pkgconfig
endif

# ---------------------------------------------------------------------------
# Measurement loop (see test/bench/README.md for every variable below)
# ---------------------------------------------------------------------------
BUILD_DIR ?= build
BENCH_DIR := test/bench
RESULTS_DIR ?= $(BENCH_DIR)/results
# Isolated CLI parser cache so concurrent runs never share ~/.cache/tree-sitter (R2-036)
export TREE_SITTER_LIBDIR ?= $(abspath $(BUILD_DIR)/ts-libdir)
# NIXPKGS_PATH is what the precedence oracle, ci.yml and flake.nix use; accept it too
NIXPKGS ?= $(if $(NIXPKGS_PATH),$(NIXPKGS_PATH),../nixpkgs)
JOBS ?= $(shell nproc 2>/dev/null || echo 4)
BASELINE ?= $(BENCH_DIR)/baseline.json
# bytes/node is deterministic; wall-clock is not, so it gets a wider gate
THRESHOLD ?= 1.05
BENCH_THRESHOLD ?= 1.10
BASELINE_SO ?=
BENCH_RUNS ?= 10
BENCH_WARMUP ?= 2
MEMORY_LIST ?= $(BENCH_DIR)/sample2000.txt
INCR_NPOS ?= 10
INCR_MAX ?= 0
FUZZ_SEED ?= 20260831
FUZZ_EDITS ?= 10
FUZZ_ITERATIONS ?= 300
PATHO_PROFILE ?= ci
PATHO_QUADRATIC ?= 0
SAN_FLAGS ?= -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer

# libtree-sitter for the C harnesses. Resolution order:
#   1. TREE_SITTER_SRC=<checkout of tree-sitter/tree-sitter> (lib/src/lib.c + lib/include)
#   2. pkg-config tree-sitter >= 0.25 (the first release that loads ABI 15)
#   3. download the release tarball matching `$(TS) --version` into $(BUILD_DIR)
# Only 1 and 3 give the private headers rawwalk.c needs (hidden-node count).
TS_VERSION := $(shell $(TS) --version 2>/dev/null | awk '{print $$2}')
TREE_SITTER_SRC ?=
ifeq ($(TREE_SITTER_SRC),)
  ifeq ($(shell pkg-config --atleast-version=0.25 tree-sitter 2>/dev/null && echo yes),yes)
    TS_PKGCONFIG := 1
  else
    TREE_SITTER_SRC := $(BUILD_DIR)/tree-sitter-$(TS_VERSION)
  endif
endif
ifeq ($(TS_PKGCONFIG),1)
  TS_CFLAGS := $(shell pkg-config --cflags tree-sitter)
  TS_LDLIBS := $(shell pkg-config --libs tree-sitter) -ldl
  TS_LIB_OBJ :=
  TS_LIB_SRC :=
  RAWWALK :=
else
  TS_CFLAGS := -I$(TREE_SITTER_SRC)/lib/include -I$(TREE_SITTER_SRC)/lib/src
  TS_LIB_SRC := $(TREE_SITTER_SRC)/lib/src/lib.c
  TS_LIB_OBJ := $(BUILD_DIR)/libtree-sitter.o
  TS_LDLIBS := $(TS_LIB_OBJ) -ldl -lpthread
  RAWWALK := $(BUILD_DIR)/rawwalk
endif
HARNESS_CFLAGS := -O2 -g -std=gnu11 -Wall $(TS_CFLAGS)
PARSER_SO := $(BUILD_DIR)/nix.so

all: lib$(LANGUAGE_NAME).a lib$(LANGUAGE_NAME).$(SOEXT) $(LANGUAGE_NAME).pc

help:
	@echo "tree-sitter-nix $(VERSION) — targets:"
	@echo "  all            build lib$(LANGUAGE_NAME).{a,$(SOEXT)} and the pkg-config file"
	@echo "  install        install into PREFIX=$(PREFIX)"
	@echo "  test           tree-sitter test + compile the queries/*.scm files"
	@echo "  oracle         operator precedence oracle vs nix-instantiate (NIXPKGS_PATH)"
	@echo "  differential   accept/reject differential vs nix/rnix/snix corpora (CORPORA_DIR, JOBS)"
	@echo "  shape-oracle   AST shape oracle on a nixpkgs sample (NIXPKGS, JOBS)"
	@echo "  bench          interleaved parse timing over test/bench/sample2000.txt vs BASELINE (BENCH_THRESHOLD, BASELINE_SO; CLI >= 0.27)"
	@echo "  memory         bytes/node, hidden nodes and RSS vs BASELINE (MEMORY_LIST)"
	@echo "  incremental    incremental == fresh reparse over test/bench/incremental-sample.txt (INCR_NPOS, INCR_MAX)"
	@echo "  fuzz           tree-sitter fuzz with a fixed seed (FUZZ_SEED, FUZZ_EDITS, FUZZ_ITERATIONS)"
	@echo "  fuzz-asan      ASan/UBSan parse of the corpus + pathological inputs (PATHO_PROFILE, PATHO_QUADRATIC)"
	@echo "  bench-baseline rewrite $(BASELINE) from the last bench + memory + incremental results (NIXPKGS)"
	@echo "  clean          remove build products (build/ and $(RESULTS_DIR) included)"
	@echo "variables: TS=$(TS) NIXPKGS=$(NIXPKGS) BUILD_DIR=$(BUILD_DIR) TREE_SITTER_SRC=$(TREE_SITTER_SRC)"

lib$(LANGUAGE_NAME).a: $(OBJS)
	$(AR) $(ARFLAGS) $@ $^

lib$(LANGUAGE_NAME).$(SOEXT): $(OBJS)
	$(CC) $(LDFLAGS) $(LINKSHARED) $^ $(LDLIBS) -o $@
ifneq ($(STRIP),)
	$(STRIP) $@
endif

$(LANGUAGE_NAME).pc: bindings/c/$(LANGUAGE_NAME).pc.in
	sed -e 's|@PROJECT_VERSION@|$(VERSION)|' \
		-e 's|@CMAKE_INSTALL_LIBDIR@|$(LIBDIR:$(PREFIX)/%=%)|' \
		-e 's|@CMAKE_INSTALL_INCLUDEDIR@|$(INCLUDEDIR:$(PREFIX)/%=%)|' \
		-e 's|@PROJECT_DESCRIPTION@|$(DESCRIPTION)|' \
		-e 's|@PROJECT_HOMEPAGE_URL@|$(HOMEPAGE_URL)|' \
		-e 's|@CMAKE_INSTALL_PREFIX@|$(PREFIX)|' $< > $@

$(PARSER): $(SRC_DIR)/grammar.json
	$(TS) generate $^

install: all
	install -d '$(DESTDIR)$(DATADIR)'/tree-sitter/queries/nix '$(DESTDIR)$(INCLUDEDIR)'/tree_sitter '$(DESTDIR)$(PCLIBDIR)' '$(DESTDIR)$(LIBDIR)'
	install -m644 bindings/c/tree_sitter/$(LANGUAGE_NAME).h '$(DESTDIR)$(INCLUDEDIR)'/tree_sitter/$(LANGUAGE_NAME).h
	install -m644 $(LANGUAGE_NAME).pc '$(DESTDIR)$(PCLIBDIR)'/$(LANGUAGE_NAME).pc
	install -m644 lib$(LANGUAGE_NAME).a '$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).a
	install -m755 lib$(LANGUAGE_NAME).$(SOEXT) '$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).$(SOEXTVER)
	ln -sf lib$(LANGUAGE_NAME).$(SOEXTVER) '$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).$(SOEXTVER_MAJOR)
	ln -sf lib$(LANGUAGE_NAME).$(SOEXTVER_MAJOR) '$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).$(SOEXT)
ifneq ($(wildcard queries/*.scm),)
	install -m644 queries/*.scm '$(DESTDIR)$(DATADIR)'/tree-sitter/queries/nix
endif

uninstall:
	$(RM) '$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).a \
		'$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).$(SOEXTVER) \
		'$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).$(SOEXTVER_MAJOR) \
		'$(DESTDIR)$(LIBDIR)'/lib$(LANGUAGE_NAME).$(SOEXT) \
		'$(DESTDIR)$(INCLUDEDIR)'/tree_sitter/$(LANGUAGE_NAME).h \
		'$(DESTDIR)$(PCLIBDIR)'/$(LANGUAGE_NAME).pc
	$(RM) -r '$(DESTDIR)$(DATADIR)'/tree-sitter/queries/nix

clean:
	$(RM) $(OBJS) $(LANGUAGE_NAME).pc lib$(LANGUAGE_NAME).a lib$(LANGUAGE_NAME).$(SOEXT)
	$(RM) -r $(BUILD_DIR) $(RESULTS_DIR)

# `tree-sitter test` exits 0 with a broken query, so each .scm is compiled explicitly
test:
	$(TS) test
	@for q in queries/*.scm; do \
		$(TS) query "$$q" test/highlight/basic.nix > /dev/null || exit 1; \
		echo "query ok: $$q"; \
	done

# ---- oracles (scripts owned by test/oracle/) --------------------------------
oracle:
	TS_BIN="$${TS_BIN:-$(TS)}" python3 test/oracle/operator_precedence_oracle.py .

differential:
	sh test/oracle/fetch-corpora.sh && TS_BIN="$${TS_BIN:-$(TS)}" python3 test/oracle/differential.py --jobs $(JOBS)

shape-oracle:
	TS_BIN="$${TS_BIN:-$(TS)}" NIXPKGS="$(NIXPKGS)" python3 test/oracle/shape/compare.py --jobs $(JOBS) test/oracle/shape/sample.txt

# ---- shared build products --------------------------------------------------
$(BUILD_DIR) $(RESULTS_DIR):
	mkdir -p $@

# The parser itself, compiled by the CLI exactly like a consumer would load it.
$(PARSER_SO): $(PARSER) $(EXTRAS) | $(BUILD_DIR)
	$(TS) build -o $@

# Release tarball of the CLI's version: curl first, gh as fallback (private networks).
$(BUILD_DIR)/tree-sitter-$(TS_VERSION)/lib/src/lib.c: | $(BUILD_DIR)
	@test -n "$(TS_VERSION)" || { echo "tree-sitter CLI not found (TS=$(TS)); set TS= or TREE_SITTER_SRC=" >&2; exit 1; }
	@echo "fetching tree-sitter v$(TS_VERSION) sources into $(BUILD_DIR)/"
	curl -fsSL -o $(BUILD_DIR)/tree-sitter-$(TS_VERSION).tar.gz \
		https://github.com/tree-sitter/tree-sitter/archive/refs/tags/v$(TS_VERSION).tar.gz \
	|| gh release download v$(TS_VERSION) -R tree-sitter/tree-sitter --archive tar.gz \
		-O $(BUILD_DIR)/tree-sitter-$(TS_VERSION).tar.gz
	tar -xzf $(BUILD_DIR)/tree-sitter-$(TS_VERSION).tar.gz -C $(BUILD_DIR)
	touch $@

ifneq ($(TS_LIB_OBJ),)
$(TS_LIB_OBJ): $(TS_LIB_SRC) | $(BUILD_DIR)
	$(CC) -O2 -g -std=gnu11 -fPIC $(TS_CFLAGS) -c $< -o $@
endif

$(BUILD_DIR)/incr_harness: $(BENCH_DIR)/incr_harness.c $(TS_LIB_OBJ) | $(BUILD_DIR)
	$(CC) $(HARNESS_CFLAGS) $< $(TS_LDLIBS) -o $@

$(BUILD_DIR)/mem_harness: $(BENCH_DIR)/harness.c $(TS_LIB_OBJ) | $(BUILD_DIR)
	$(CC) $(HARNESS_CFLAGS) $< $(TS_LDLIBS) -o $@

$(BUILD_DIR)/rawwalk: $(BENCH_DIR)/rawwalk.c $(TS_LIB_OBJ) | $(BUILD_DIR)
	$(CC) $(HARNESS_CFLAGS) $< $(TS_LDLIBS) -o $@

# Sanitized static build: library + parser + scanner all instrumented.
$(BUILD_DIR)/asan_harness: $(BENCH_DIR)/asan_harness.c $(TS_LIB_SRC) $(PARSER) $(EXTRAS) | $(BUILD_DIR)
ifeq ($(TS_PKGCONFIG),1)
	$(CC) -O1 -g -std=gnu11 $(SAN_FLAGS) -I$(SRC_DIR) $(TS_CFLAGS) $(BENCH_DIR)/asan_harness.c $(PARSER) $(EXTRAS) $(TS_LDLIBS) -o $@
else
	$(CC) -O1 -g -std=gnu11 $(SAN_FLAGS) -I$(SRC_DIR) $(TS_CFLAGS) $(BENCH_DIR)/asan_harness.c $(TS_LIB_SRC) $(PARSER) $(EXTRAS) -ldl -lpthread -o $@
endif

# ---- measurement targets ----------------------------------------------------
bench: $(PARSER_SO) | $(RESULTS_DIR)
	NIXPKGS="$(NIXPKGS)" TS="$(TS)" RUNS=$(BENCH_RUNS) WARMUP=$(BENCH_WARMUP) RESULTS="$(RESULTS_DIR)" \
		sh $(BENCH_DIR)/bench.sh $(PARSER_SO) $(BASELINE_SO)
	python3 $(BENCH_DIR)/compare_bench.py --baseline $(BASELINE) --threshold $(BENCH_THRESHOLD) $(RESULTS_DIR)/bench.json

memory: $(PARSER_SO) $(BUILD_DIR)/mem_harness $(RAWWALK) | $(RESULTS_DIR)
	NIXPKGS="$(NIXPKGS)" RESULTS="$(RESULTS_DIR)" LIST="$(MEMORY_LIST)" RAWWALK="$(RAWWALK)" \
		sh $(BENCH_DIR)/memory.sh $(BUILD_DIR)/mem_harness $(PARSER_SO)
	python3 $(BENCH_DIR)/compare_memory.py --baseline $(BASELINE) --threshold $(THRESHOLD) $(RESULTS_DIR)

incremental: $(PARSER_SO) $(BUILD_DIR)/incr_harness | $(RESULTS_DIR)
	sed 's|^|$(NIXPKGS)/|' $(BENCH_DIR)/incremental-sample.txt > $(BUILD_DIR)/incremental-files.txt
	rm -rf $(RESULTS_DIR)/incremental && mkdir -p $(RESULTS_DIR)/incremental
	$(BUILD_DIR)/incr_harness --npos $(INCR_NPOS) --max-mismatches $(INCR_MAX) \
		--out $(RESULTS_DIR)/incremental --files $(BUILD_DIR)/incremental-files.txt $(PARSER_SO)

# `tree-sitter fuzz` exits 0 even when a parse is wrong (R1-067): grep its output.
fuzz: | $(RESULTS_DIR)
	TREE_SITTER_SEED=$(FUZZ_SEED) $(TS) fuzz --edits $(FUZZ_EDITS) --iterations $(FUZZ_ITERATIONS) 2>&1 | tee $(RESULTS_DIR)/fuzz.log
	@! grep -qE 'Incorrect|failed fuzzing|panicked' $(RESULTS_DIR)/fuzz.log
	@echo "fuzz ok (seed $(FUZZ_SEED))"

fuzz-asan: $(BUILD_DIR)/asan_harness | $(RESULTS_DIR)
	python3 $(BENCH_DIR)/gen_patho.py --profile $(PATHO_PROFILE) --corpus test/corpus $(BUILD_DIR)/patho
	$(BUILD_DIR)/asan_harness --report $(RESULTS_DIR)/asan.tsv \
		$(BUILD_DIR)/patho/*.nix $(BENCH_DIR)/patho/*.nix \
		$(if $(filter 1,$(PATHO_QUADRATIC)),$(BENCH_DIR)/patho/quadratic/*.nix)

bench-baseline:
	TS_VERSION=$(TS_VERSION) python3 $(BENCH_DIR)/compare_bench.py --write-baseline $(BASELINE) --parser $(PARSER) --nixpkgs "$(NIXPKGS)" $(RESULTS_DIR)

.PHONY: all help install uninstall clean test oracle differential shape-oracle \
	bench memory incremental fuzz fuzz-asan bench-baseline
