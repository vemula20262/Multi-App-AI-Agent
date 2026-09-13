import { describe, expect, it } from "vitest";
import { encodeWav } from "./audio";
describe("local microphone WAV conversion", () => {
  it("encodes one second of 48 kHz audio as 16 kHz mono PCM16", () => {
    const wav = encodeWav(new Float32Array(48000).fill(0.5), 48000);
    const view = new DataView(wav);
    expect(wav.byteLength).toBe(32044);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getInt16(44, true)).toBe(16383);
  });
  it("clips extreme samples without overflowing", () => {
    const view = new DataView(encodeWav(new Float32Array([-2, 2]), 16000));
    expect(view.getInt16(44, true)).toBe(-32768);
    expect(view.getInt16(46, true)).toBe(32767);
  });
});
