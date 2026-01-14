import formatTimeSince from './formatTimeSince';
import { getLocalStorage, setLocalStorage } from './localStorage';
import { cleanupExpiredSessionConfig, getSessionConfig, setSessionConfig } from './sessionConfig';

const UTILS = {
  formatTimeSince,
  getLocalStorage,
  setLocalStorage,
  getSessionConfig,
  setSessionConfig,
  cleanupExpiredSessionConfig,
};

export default UTILS;
