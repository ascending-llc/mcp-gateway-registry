import {exec} from "node:child_process";
import {promisify} from "node:util";
import path from "node:path";

const execAsync = promisify(exec);

export interface TokenRefreshResult {
  success: boolean;
  message: string;
}

/**
 * Automatically refresh OAuth tokens by calling generate_creds.sh
 * @param projectRoot - Path to the project root directory
 * @returns Result of the token refresh operation
 */
export async function refreshTokens(projectRoot?: string): Promise<TokenRefreshResult> {
  try {
    // Default to parent of cli directory
    const root = projectRoot || path.join(process.cwd(), "..");
    const scriptPath = path.join(root, "credentials-provider", "generate_creds.sh");

    // Check if script exists
    try {
      await execAsync(`test -f "${scriptPath}"`);
    } catch {
      return {
        success: false,
        message: `Token refresh script not found at ${scriptPath}`
      };
    }

    // Run the script with --ingress-only and --force flags
    const {stdout, stderr} = await execAsync(
      `cd "${root}" && ./credentials-provider/generate_creds.sh --ingress-only --force`,
      {
        timeout: 30000, // 30 second timeout
        maxBuffer: 1024 * 1024 // 1MB buffer
      }
    );

    // Check if successful by looking for success indicators in output
    const output = stdout + stderr;
    if (output.includes("Successfully") || output.includes("Token generated") || output.includes("Tokens saved")) {
      return {
        success: true,
        message: "OAuth tokens refreshed successfully"
      };
    }

    return {
      success: false,
      message: `Token refresh completed but status unclear: ${output.substring(0, 200)}`
    };
  } catch (error: any) {
    return {
      success: false,
      message: `Failed to refresh tokens: ${error.message}`
    };
  }
}

/**
 * Check if we should attempt automatic token refresh
 * @param secondsRemaining - Seconds until token expires
 * @returns true if we should refresh
 */
export function shouldRefreshToken(secondsRemaining: number | undefined): boolean {
  // Refresh if token expires in less than 10 seconds or already expired
  return secondsRemaining !== undefined && secondsRemaining <= 10;
}
