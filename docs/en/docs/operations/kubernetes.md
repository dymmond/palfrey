# Kubernetes

This page covers production-grade Kubernetes deployment patterns for Palfrey.

## Deployment Manifest

A standard Palfrey deployment uses a `Deployment` object to manage a set of identical pods.

```yaml
{!> ../../../docs_src/kubernetes/deployment.yaml !}
```

### Resource requests and limits

Configuring resources ensures the Kubernetes scheduler can place your pods appropriately and prevents a single pod from consuming all node resources.

- **CPU**: Palfrey is efficient but benefits from dedicated CPU time. Start with `100m` request and scale based on load.
- **Memory**: Depends on your application logic. Palfrey itself has a small footprint (~30-50MB), but your app and dependencies will drive this.

## Service

Expose your Palfrey pods within the cluster using a `Service`.

```yaml
{!> ../../../docs_src/kubernetes/service.yaml !}
```

## Health Checks

Kubernetes uses probes to determine if a container is alive and ready to serve traffic.

### Liveness and readiness probes

- **Liveness**: Restarts the container if it fails.
- **Readiness**: Stops sending traffic to the pod if it fails (e.g., during startup or high load).

Example ASGI health check implementation:

```python
{!> ../../../docs_src/kubernetes/health-check.py !}
```

## Scaling (HPA)

Automatically scale the number of pods based on CPU utilization or custom metrics.

```yaml
{!> ../../../docs_src/kubernetes/hpa.yaml !}
```

## Configuration

Manage Palfrey configuration using `ConfigMap` and `Secrets`.

```yaml
{!> ../../../docs_src/kubernetes/configmap.yaml !}
```

Palfrey automatically picks up environment variables like `WEB_CONCURRENCY` and `FORWARDED_ALLOW_IPS`.

## Graceful Shutdown

Palfrey handles `SIGTERM` for graceful shutdown. In Kubernetes, you should coordinate this with the `terminationGracePeriodSeconds` and potentially a `preStop` hook to ensure the ingress controller stops sending traffic before the process exits.

1. **SIGTERM**: Kubernetes sends this signal to the process. Palfrey stops accepting new connections and finishes active ones.
2. **preStop Hook**: A small sleep (e.g., 5-10s) in a `preStop` hook gives time for service endpoints to update across the cluster.
3. **Grace Period**: Ensure `terminationGracePeriodSeconds` is longer than your `preStop` sleep plus your app's expected cleanup time.

## Multi-worker Considerations

In a Kubernetes environment, you have two ways to scale:

1. **Vertical**: Increase `--workers N` inside a single pod.
2. **Horizontal**: Increase the number of pod `replicas` (recommended).

**Recommended Pattern**:
Keep pods small (e.g., 1-2 workers) and scale horizontally using more replicas. This provides better granularity for the autoscaler and higher resilience if a single node fails.

## Non-technical summary

Kubernetes provides the "hardware" for your Palfrey application.
By defining how Palfrey runs, scales, and recovers from failure, you ensure your service remains available and responsive to users.
