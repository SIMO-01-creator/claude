import Anthropic from '@anthropic-ai/sdk';
import { promptFeedback } from './feedback';

const client = new Anthropic();

async function main() {
  const message = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1024,
    messages: [{ role: 'user', content: 'Hello, Claude!' }],
  });

  console.log(message.content);

  await promptFeedback();
}

main().catch(console.error);
