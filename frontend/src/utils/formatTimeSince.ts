const formatTimeSince = (timestamp: string | null | undefined): string | null => {
  if (!timestamp) {
    return null;
  }

  try {
    const now = new Date();
    const lastChecked = new Date(timestamp.endsWith('Z') ? timestamp : `${timestamp}Z`);

    // Check if the date is valid
    if (Number.isNaN(lastChecked.getTime())) {
      return null;
    }

    const diffMs = now.getTime() - lastChecked.getTime();

    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    let result: string | null = null;
    if (diffDays > 0) {
      result = `${diffDays}d ago`;
    } else if (diffHours > 0) {
      result = `${diffHours}h ago`;
    } else if (diffMinutes > 0) {
      result = `${diffMinutes}m ago`;
    } else {
      result = `${diffSeconds}s ago`;
    }

    return result;
  } catch (_error) {
    return null;
  }
};

export default formatTimeSince;
