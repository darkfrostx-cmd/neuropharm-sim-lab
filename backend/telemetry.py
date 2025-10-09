"""OpenTelemetry bootstrap utilities for the Neuropharm backend."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Callable, List, Optional

from .config import TelemetryConfig

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


@dataclass
class TelemetryManager:
    """Configure tracing/metrics exporters when the SDK is available."""

    config: TelemetryConfig
    _shutdown_hooks: List[Callable[[], None]] = field(default_factory=list)
    _instrument_fastapi: Optional[Callable[["FastAPI"], None]] = None
    _enabled: bool = False

    def __post_init__(self) -> None:
        # Ensure the shutdown hook list exists even when dataclass bypasses init.
        if self._shutdown_hooks is None:
            self._shutdown_hooks = []

    def configure(self) -> None:
        if not self.config.capture_traces and not self.config.capture_metrics:
            LOGGER.debug("Telemetry disabled by configuration")
            return
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        except ImportError:
            LOGGER.warning("OpenTelemetry SDK not available; telemetry disabled")
            return

        resource = Resource.create(
            {
                "service.name": self.config.service_name,
                "deployment.environment": self.config.environment,
            }
        )
        sampler = TraceIdRatioBased(max(min(self.config.sampling_ratio, 1.0), 0.0))
        provider = TracerProvider(resource=resource, sampler=sampler)
        if self.config.capture_traces:
            try:
                span_exporter = OTLPSpanExporter(
                    endpoint=self.config.exporter_endpoint,
                    protocol=self.config.exporter_protocol,
                )
                provider.add_span_processor(BatchSpanProcessor(span_exporter))
                LOGGER.info("OpenTelemetry tracing configured (endpoint=%s)", self.config.exporter_endpoint)
                self._shutdown_hooks.append(provider.shutdown)
                trace.set_tracer_provider(provider)
            except Exception as exc:  # pragma: no cover - exporter wiring
                LOGGER.warning("Failed to initialise OTLP span exporter: %s", exc)
        if self.config.capture_metrics:
            try:
                metric_exporter = OTLPMetricExporter(
                    endpoint=self.config.exporter_endpoint,
                    protocol=self.config.exporter_protocol,
                )
                reader = PeriodicExportingMetricReader(metric_exporter)
                meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
                metrics.set_meter_provider(meter_provider)
                LOGGER.info("OpenTelemetry metrics configured (endpoint=%s)", self.config.exporter_endpoint)
                self._shutdown_hooks.append(meter_provider.shutdown)  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover - exporter wiring
                LOGGER.warning("Failed to initialise OTLP metric exporter: %s", exc)

        # Instrument FastAPI lazily – the caller must pass the app instance.
        self._instrument_fastapi = FastAPIInstrumentor().instrument_app  # type: ignore[attr-defined]
        self._enabled = True

    def instrument_app(self, app: "FastAPI") -> None:
        if not getattr(self, "_instrument_fastapi", None):
            return
        try:
            self._instrument_fastapi(app)
        except Exception as exc:  # pragma: no cover - instrumentation failure
            LOGGER.warning("Failed to instrument FastAPI: %s", exc)

    def shutdown(self) -> None:
        for hook in reversed(self._shutdown_hooks or []):
            try:
                hook()
            except Exception:  # pragma: no cover - best effort cleanup
                continue


def configure_telemetry(config: TelemetryConfig) -> TelemetryManager:
    manager = TelemetryManager(config=config)
    manager.configure()
    return manager

