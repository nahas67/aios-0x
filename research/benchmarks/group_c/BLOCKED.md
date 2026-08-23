# Group C - BLOCKED pending infrastructure

Formal NATS JetStream vs Redpanda vs Redis Streams throughput benchmarks
(10k-100k msg/sec per Phase 2B) require running broker services that are not
available in this environment:

- nats-server: Go binary (source zip present in OSS archive; not built)
- redpanda / redis: no local service runtime provisioned

## Unblock requirements
1. Docker Desktop or native service installs for one or more brokers
2. nats-py client (pip) + benchmark producer/consumer harness per template
3. Protocol runs: >=3 warmups discarded, >=10 repetitions, p50/p95/p99

## Interim decision impact
- InMemoryEventBus remains the validated local transport (tests green at
  replay scale); no formal selection is blocked beyond durable deployment,
  which is a later-phase concern anyway.
