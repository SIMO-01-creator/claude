import { Readable, Writable } from 'stream';
import { promptFeedback, FeedbackResult } from './feedback';

function makeStreams(input: string): { readable: Readable; writable: Writable; output: string[] } {
  const output: string[] = [];
  const readable = Readable.from([input]);
  const writable = new Writable({
    write(chunk, _enc, cb) {
      output.push(chunk.toString());
      cb();
    },
  });
  return { readable, writable, output };
}

describe('promptFeedback', () => {
  it('returns submitted: true with the message when the user types feedback', async () => {
    const { readable, writable } = makeStreams('Great tool!\n');
    const result: FeedbackResult = await promptFeedback(readable, writable);
    expect(result.submitted).toBe(true);
    expect(result.message).toBe('Great tool!');
  });

  it('returns submitted: false when the user presses Enter without typing', async () => {
    const { readable, writable } = makeStreams('\n');
    const result = await promptFeedback(readable, writable);
    expect(result.submitted).toBe(false);
    expect(result.message).toBeUndefined();
  });

  it('trims whitespace from the feedback message', async () => {
    const { readable, writable } = makeStreams('  needs improvement  \n');
    const result = await promptFeedback(readable, writable);
    expect(result.submitted).toBe(true);
    expect(result.message).toBe('needs improvement');
  });

  it('prints a thank-you message after receiving feedback', async () => {
    const { readable, writable, output } = makeStreams('Loving it!\n');
    await promptFeedback(readable, writable);
    expect(output.join('')).toContain('Thank you for your feedback!');
  });

  it('does not print a thank-you message when skipped', async () => {
    const { readable, writable, output } = makeStreams('\n');
    await promptFeedback(readable, writable);
    expect(output.join('')).not.toContain('Thank you');
  });
});
