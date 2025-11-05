import { BedrockRuntimeClient } from "@aws-sdk/client-bedrock-runtime";

let cachedClient: BedrockRuntimeClient | null = null;

export function getBedrockClient(): BedrockRuntimeClient {
  if (cachedClient) {
    return cachedClient;
  }

  // AWS SDK will automatically use credentials from environment variables:
  // AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
  // Or from ~/.aws/credentials or EC2/ECS instance metadata
  const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1";

  // Support for explicit profile
  const profile = process.env.AWS_PROFILE;

  const clientConfig: any = {
    region
  };

  // If a profile is specified, let the SDK handle it
  if (profile) {
    // The AWS SDK will automatically load credentials from the profile
    clientConfig.profile = profile;
  }

  cachedClient = new BedrockRuntimeClient(clientConfig);

  return cachedClient;
}
