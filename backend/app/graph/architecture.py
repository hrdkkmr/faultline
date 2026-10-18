"""Architecture-derived topology for Online Boutique (the system used by RCAEval RE*-OB).

Source of every DEPENDS_ON edge: the `*_SERVICE_ADDR` / `REDIS_ADDR` environment variables in
GoogleCloudPlatform/microservices-demo `release/kubernetes-manifests.yaml` (Apache-2.0).
An env var `X_SERVICE_ADDR` on deployment A means "A is configured to call X".
These edges are *architecture-derived*: they are not claimed to be observed in benchmark traces.
Trace-observed calls are stored separately as CALLS edges.

`otel_counterpart` maps each service to the closest OpenTelemetry Astronomy Shop service
(open-telemetry/opentelemetry-demo). The identifiers differ; the mapping is for reference only.
"""

from __future__ import annotations

SYSTEM_ID = "online-boutique"
MANIFEST_REF = (
    "https://github.com/GoogleCloudPlatform/microservices-demo/blob/main/release/kubernetes-manifests.yaml"
)

SERVICES: dict[str, dict] = {
    "frontend-external": {"kind": "entrypoint", "language": "k8s LoadBalancer", "otel_counterpart": "frontend-proxy"},
    "frontend": {"kind": "service", "language": "Go", "otel_counterpart": "frontend"},
    "cartservice": {"kind": "service", "language": "C#", "otel_counterpart": "cart"},
    "productcatalogservice": {"kind": "service", "language": "Go", "otel_counterpart": "product-catalog"},
    "currencyservice": {"kind": "service", "language": "Node.js", "otel_counterpart": "currency"},
    "paymentservice": {"kind": "service", "language": "Node.js", "otel_counterpart": "payment"},
    "shippingservice": {"kind": "service", "language": "Go", "otel_counterpart": "shipping"},
    "emailservice": {"kind": "service", "language": "Python", "otel_counterpart": "email"},
    "checkoutservice": {"kind": "service", "language": "Go", "otel_counterpart": "checkout"},
    "recommendationservice": {"kind": "service", "language": "Python", "otel_counterpart": "recommendation"},
    "adservice": {"kind": "service", "language": "Java", "otel_counterpart": "ad"},
    "redis": {"kind": "datastore", "language": "Redis (redis-cart)", "otel_counterpart": "valkey-cart"},
}

# (caller, callee, evidence in the manifest)
DEPENDS_ON: list[tuple[str, str, str]] = [
    ("frontend-external", "frontend", "Service frontend-external targets frontend pods"),
    ("frontend", "productcatalogservice", "frontend env PRODUCT_CATALOG_SERVICE_ADDR"),
    ("frontend", "currencyservice", "frontend env CURRENCY_SERVICE_ADDR"),
    ("frontend", "cartservice", "frontend env CART_SERVICE_ADDR"),
    ("frontend", "recommendationservice", "frontend env RECOMMENDATION_SERVICE_ADDR"),
    ("frontend", "shippingservice", "frontend env SHIPPING_SERVICE_ADDR"),
    ("frontend", "checkoutservice", "frontend env CHECKOUT_SERVICE_ADDR"),
    ("frontend", "adservice", "frontend env AD_SERVICE_ADDR"),
    ("checkoutservice", "productcatalogservice", "checkoutservice env PRODUCT_CATALOG_SERVICE_ADDR"),
    ("checkoutservice", "shippingservice", "checkoutservice env SHIPPING_SERVICE_ADDR"),
    ("checkoutservice", "paymentservice", "checkoutservice env PAYMENT_SERVICE_ADDR"),
    ("checkoutservice", "emailservice", "checkoutservice env EMAIL_SERVICE_ADDR"),
    ("checkoutservice", "currencyservice", "checkoutservice env CURRENCY_SERVICE_ADDR"),
    ("checkoutservice", "cartservice", "checkoutservice env CART_SERVICE_ADDR"),
    ("recommendationservice", "productcatalogservice", "recommendationservice env PRODUCT_CATALOG_SERVICE_ADDR"),
    ("cartservice", "redis", "cartservice env REDIS_ADDR=redis-cart:6379"),
]
