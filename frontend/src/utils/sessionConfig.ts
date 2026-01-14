const SESSION_CONFIG: Record<string, string> = {};

export const setSessionConfig = (key: string, value: any, expireMinutes?: number) => {
  const now = Date.now();
  const expireTime = expireMinutes !== undefined && expireMinutes !== null ? now + expireMinutes * 60 * 1000 : null;

  const data = { value: value, expire: expireTime };

  SESSION_CONFIG[key] = JSON.stringify(data);
};

export const getSessionConfig = (key: string) => {
  const dataStr = SESSION_CONFIG[key];
  if (!dataStr) return null;

  try {
    const data = JSON.parse(dataStr);
    const now = Date.now();

    if (data.expire !== null && now > data.expire) {
      delete SESSION_CONFIG[key];
      return null;
    }

    return data.value;
  } catch (_error) {
    delete SESSION_CONFIG[key];
    return null;
  }
};

export const cleanupExpiredSessionConfig = () => {
  const now = Date.now();
  Object.keys(SESSION_CONFIG).forEach(key => {
    try {
      const data = JSON.parse(SESSION_CONFIG[key]);
      if (data.expire !== null && now > data.expire) {
        delete SESSION_CONFIG[key];
      }
    } catch (_error) {
      delete SESSION_CONFIG[key];
    }
  });
};
