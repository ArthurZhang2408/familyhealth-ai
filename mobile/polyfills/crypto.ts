/**
 * WebCrypto polyfill for React Native / Expo Go.
 *
 * Expo Go's Hermes runtime doesn't expose crypto.subtle, which Supabase needs
 * for PKCE code challenge generation (SHA-256). We implement it using
 * expo-crypto's digestStringAsync, which calls the platform's native crypto.
 *
 * Must be imported before any Supabase code runs — see index.js.
 */
import * as ExpoCrypto from 'expo-crypto';

if (typeof globalThis.crypto === 'undefined' || !globalThis.crypto?.subtle) {
  const algorithmMap: Record<string, ExpoCrypto.CryptoDigestAlgorithm> = {
    'SHA-1':   ExpoCrypto.CryptoDigestAlgorithm.SHA1,
    SHA1:      ExpoCrypto.CryptoDigestAlgorithm.SHA1,
    'SHA-256': ExpoCrypto.CryptoDigestAlgorithm.SHA256,
    SHA256:    ExpoCrypto.CryptoDigestAlgorithm.SHA256,
    'SHA-384': ExpoCrypto.CryptoDigestAlgorithm.SHA384,
    SHA384:    ExpoCrypto.CryptoDigestAlgorithm.SHA384,
    'SHA-512': ExpoCrypto.CryptoDigestAlgorithm.SHA512,
    SHA512:    ExpoCrypto.CryptoDigestAlgorithm.SHA512,
  };

  const subtle = {
    async digest(algorithm: AlgorithmIdentifier, data: BufferSource): Promise<ArrayBuffer> {
      const name = typeof algorithm === 'string' ? algorithm : algorithm.name;
      const expoAlg = algorithmMap[name];
      if (!expoAlg) throw new Error(`crypto.subtle.digest: unsupported algorithm "${name}"`);

      // Convert BufferSource → string.
      // PKCE code verifiers are ASCII-only (base64url), so charCode is correct.
      const bytes = ArrayBuffer.isView(data)
        ? new Uint8Array(data.buffer as ArrayBuffer, data.byteOffset, data.byteLength)
        : new Uint8Array(data as ArrayBuffer);
      const str = Array.from(bytes, (b) => String.fromCharCode(b)).join('');

      // digestStringAsync hashes the UTF-8 bytes of the string — same as
      // what crypto.subtle.digest receives from TextEncoder.encode(str).
      const hex = await ExpoCrypto.digestStringAsync(expoAlg, str, {
        encoding: ExpoCrypto.CryptoEncoding.HEX,
      });

      // Hex string → ArrayBuffer
      const out = new Uint8Array(hex.length / 2);
      for (let i = 0; i < hex.length; i += 2) {
        out[i / 2] = parseInt(hex.slice(i, i + 2), 16);
      }
      return out.buffer as ArrayBuffer;
    },
  };

  Object.defineProperty(globalThis, 'crypto', {
    value: { getRandomValues: ExpoCrypto.getRandomValues, subtle },
    writable: true,
    configurable: true,
  });
}
