CLI = .build/il-pinocchio

PYTHON=python3
PYTHONPATH=ethsnarks/:python/

CIRCUIT_TESTS_DIR=tests/circuits/
CIRCUIT_TESTS=$(wildcard $(CIRCUIT_TESTS_DIR)/*.circuit)

all: $(CLI)

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

clean: pinocchio-clean
	rm -rf .build

test-parser:
	@for circuit_file in tests/circuits/*.circuit; do \
		echo "# Parsing $$circuit_file"; \
		PYTHONPATH=$(PYTHONPATH) $(PYTHON) -msnarkil.parser $$circuit_file; \
		PYTHONPATH=$(PYTHONPATH) $(PYTHON) -msnarkil.program $$circuit_file `echo $$circuit_file | cut -f 1 -d '.'`.input; \
		echo ""; \
	done


pinocchio-test: $(addsuffix .result, $(basename $(CIRCUIT_TESTS)))

pinocchio-clean:
	rm -f $(CIRCUIT_TESTS_DIR)/*.result

$(CIRCUIT_TESTS_DIR)/%.result: $(CIRCUIT_TESTS_DIR)/%.circuit $(CIRCUIT_TESTS_DIR)/%.test $(CIRCUIT_TESTS_DIR)/%.input $(CLI)
	$(CLI) $< eval $(basename $<).input > $@
	diff -ru $(basename $<).test $@ || rm $@
