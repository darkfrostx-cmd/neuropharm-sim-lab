import { diag, DiagConsoleLogger, DiagLogLevel, Span, SpanStatusCode, trace } from '@opentelemetry/api'

type TelemetryOptions = {
  serviceName: string
  environment?: string
  enabled: boolean
}

let configured = false
let cachedTracer: ReturnType<typeof trace.getTracer> | null = null

diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.ERROR)

export function ensureTelemetry(options: TelemetryOptions): void {
  if (configured || !options.enabled) {
    if (!cachedTracer) {
      cachedTracer = trace.getTracer(options.serviceName)
    }
    return
  }
  cachedTracer = trace.getTracer(options.serviceName, { version: '1.0.0' })
  configured = true
}

export async function withSpan<T>(
  name: string,
  attributes: Record<string, unknown>,
  fn: (span: Span | undefined) => Promise<T>,
): Promise<T> {
  const tracer = cachedTracer ?? trace.getTracer('neuropharm-worker')
  return tracer.startActiveSpan(name, async (span) => {
    try {
      Object.entries(attributes || {}).forEach(([key, value]) => {
        span.setAttribute(key, value as never)
      })
      const result = await fn(span)
      span.setStatus({ code: SpanStatusCode.OK })
      return result
    } catch (error) {
      span.recordException(error as Error)
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message })
      throw error
    } finally {
      span.end()
    }
  })
}
