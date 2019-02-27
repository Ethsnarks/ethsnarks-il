CLI = .build/il-pinocchio

PYTHON=python3
PYTHONPATH=ethsnarks/:python/

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

clean:
	rm -rf .build

test-parser:
	@for circuit_file in tests/circuits/*.circuit; do \
		echo "# Parsing $$circuit_file"; \
		PYTHONPATH=$(PYTHONPATH) $(PYTHON) -msnarkil.parser $$circuit_file; \
		echo ""; \
	done
