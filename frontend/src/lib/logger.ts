const IS_DEV = import.meta.env.DEV

type Level = 'debug' | 'info' | 'warn' | 'error'

const PREFIX = (level: Level) =>
  `${new Date().toTimeString().slice(0, 8)} [${level.toUpperCase().padEnd(5)}]`

export const logger = {
  debug: (...args: unknown[]) =>
    IS_DEV && console.debug(PREFIX('debug'), ...args),
  info: (...args: unknown[]) =>
    IS_DEV && console.info(PREFIX('info'), ...args),
  warn: (...args: unknown[]) =>
    IS_DEV && console.warn(PREFIX('warn'), ...args),
  error: (...args: unknown[]) =>
    IS_DEV && console.error(PREFIX('error'), ...args),
}

export default logger
