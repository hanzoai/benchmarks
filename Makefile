GO      ?= go
GOFLAGS ?= -mod=mod
export GOPRIVATE = github.com/hanzoai

.PHONY: all test bench scale k3s-up k3s-down help

help: ## list targets
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## / — /' | sort

all: test bench ## property tests + throughput

scale: ## horizontal-scale proof: 1M tenants across N=3/10/100 pods (prints)
	$(GO) test $(GOFLAGS) ./cloud/shard/ -run 'ScaleProof|Deterministic|Reshuffle' -v -count=1

bench: ## routing throughput (ns/op, allocs) across ring sizes
	$(GO) test $(GOFLAGS) ./cloud/... -bench=. -benchmem -run '^$$'

test: ## all cluster-free property tests
	$(GO) test $(GOFLAGS) ./... -count=1

k3s-up: ## integration: stand up the cloud StatefulSet N=3 in local k3s
	./k3s/up.sh

k3s-down: ## tear down the local k3s shard stack
	./k3s/down.sh
