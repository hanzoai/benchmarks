.PHONY: all setup bench bench-serialize bench-agents bench-blockchain bench-inference report charts clean

all: bench

setup:
	@echo "Setting up benchmark environment..."
	cd bench-serialize && go mod tidy
	cd bench-agents && pip install -r requirements.txt
	cd bench-blockchain && go mod tidy
	@echo "Setup complete."

bench: bench-serialize bench-agents bench-blockchain bench-inference
	@echo "All benchmarks complete. Results in results/"

bench-serialize:
	@echo "Running serialization benchmarks..."
	@mkdir -p results
	cd bench-serialize && go test -bench=. -benchmem -count=10 -json > ../results/serialize.json
	cd bench-serialize && go test -bench=. -benchmem -count=10 | tee ../results/serialize.txt

bench-agents:
	@echo "Running agent benchmarks..."
	@mkdir -p results
	cd bench-agents && python benchmark_mcp_overhead.py | tee ../results/agents.json
	cd bench-agents && python benchmark_multi_agent.py | tee ../results/multi_agent.json

bench-blockchain:
	@echo "Running blockchain benchmarks..."
	@mkdir -p results
	cd bench-blockchain && go test -bench=. -benchmem -count=10 -json > ../results/blockchain.json
	cd bench-blockchain && go test -bench=. -benchmem -count=10 | tee ../results/blockchain.txt

bench-inference:
	@echo "Running inference benchmarks..."
	@mkdir -p results
	cd bench-inference && python benchmark_inference.py | tee ../results/inference.json

report:
	@echo "Generating benchmark report..."
	python scripts/generate_report.py

charts:
	@echo "Generating charts..."
	python scripts/generate_charts.py

clean:
	rm -rf results/
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
