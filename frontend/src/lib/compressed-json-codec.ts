import LZString from 'lz-string'

export interface CompressedJsonCodec {
  decode: (encoded: string) => unknown
  encode: (value: unknown) => string
}

interface CompressedJsonCodecOptions {
  maxCompressedLength: number
  maxDecompressedLength: number
}

const { compressToEncodedURIComponent } = LZString
// lz-string's declarations omit the null returned for invalid compressed input.
const decompress: (encoded: string) => string | null = LZString.decompressFromEncodedURIComponent

export function createCompressedJsonCodec({
  maxCompressedLength,
  maxDecompressedLength
}: CompressedJsonCodecOptions): CompressedJsonCodec {
  return {
    decode(encoded) {
      if (encoded.length > maxCompressedLength) return null

      const json = decompress(encoded)
      if (json == null || json.length > maxDecompressedLength) return null
      return parseJson(json)
    },
    encode(value) {
      return compressToEncodedURIComponent(JSON.stringify(value))
    }
  }
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch (error) {
    if (error instanceof SyntaxError) return null
    throw error
  }
}
