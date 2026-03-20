import * as readline from 'readline';

export interface FeedbackResult {
  submitted: boolean;
  message?: string;
}

export function promptFeedback(
  input: NodeJS.ReadableStream = process.stdin,
  output: NodeJS.WritableStream = process.stdout
): Promise<FeedbackResult> {
  const rl = readline.createInterface({ input, output });

  return new Promise((resolve) => {
    output.write('\n--- Feedback ---\n');
    output.write('Press Enter to skip, or type your feedback and press Enter:\n> ');

    let resolved = false;

    rl.once('line', (line) => {
      resolved = true;
      rl.close();
      const message = line.trim();
      if (!message) {
        resolve({ submitted: false });
      } else {
        output.write('Thank you for your feedback!\n');
        resolve({ submitted: true, message });
      }
    });

    rl.once('close', () => {
      if (!resolved) {
        resolve({ submitted: false });
      }
    });
  });
}
