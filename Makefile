CLI = .build/il-pinocchio

PYTHON=python3
PYTHONPATH=ethsnarks/:python/

CIRCUIT_TESTS_DIR=tests/circuits
CIRCUIT_TESTS=$(wildcard $(CIRCUIT_TESTS_DIR)/*.circuit)

all: $(CLI) test-circuits

$(CLI): .build
	$(MAKE) -C $(dir $@)

.build:
	mkdir -p $@
	cd $@ && cmake ../cxx/ || rm -rf ../$@

debug:
	mkdir -p .build && cd .build && cmake -DCMAKE_BUILD_TYPE=Debug ../cxx/

release:
	mkdir -p .build && cd .build && cmake -DCMAKE_BUILD_TYPE=Release ../cxx/

performance:
	mkdir -p .build && cd .build && cmake -DCMAKE_BUILD_TYPE=Release -DPERFORMANCE=1 ../cxx/

git-submodules:
	git submodule update --init --recursive

git-pull:
	git pull --recurse-submodules
	git submodule update --recursive --remote

clean: test-circuits-clean
	rm -rf .build

test: test-circuits

test-parser:
	@for circuit_file in tests/circuits/*.circuit; do \
		echo "# Parsing $$circuit_file"; \
		PYTHONPATH=$(PYTHONPATH) $(PYTHON) -msnarkil.parser $$circuit_file; \
		echo ""; \
	done

test-debugger:
	@for circuit_file in tests/circuits/*.circuit; do \
		echo "# Debugging $$circuit_file"; \
		PYTHONPATH=$(PYTHONPATH) $(PYTHON) -msnarkil.debugger $$circuit_file `echo $$circuit_file | cut -f 1 -d '.'`.input; \
		echo ""; \
	done

test-circuits: $(addsuffix .result-cxx, $(basename $(CIRCUIT_TESTS))) $(addsuffix .result-py, $(basename $(CIRCUIT_TESTS)))

test-circuits-clean:
	rm -f $(CIRCUIT_TESTS_DIR)/*.result $(CIRCUIT_TESTS_DIR)/*.result-*

# Perform circuit file tests using Python implementation
$(CIRCUIT_TESTS_DIR)/%.result-py: $(CIRCUIT_TESTS_DIR)/%.circuit $(CIRCUIT_TESTS_DIR)/%.test $(CIRCUIT_TESTS_DIR)/%.input
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -msnarkil.program $< $(basename $<).input > $@
	diff -ru $(basename $<).test $@ || rm $@

# Perform circuit file tests using C++ implementation
$(CIRCUIT_TESTS_DIR)/%.result-cxx: $(CIRCUIT_TESTS_DIR)/%.circuit $(CIRCUIT_TESTS_DIR)/%.test $(CIRCUIT_TESTS_DIR)/%.input $(CLI)
	$(CLI) $< eval $(basename $<).input > $@
	diff -ru $(basename $<).test $@ || rm $@
