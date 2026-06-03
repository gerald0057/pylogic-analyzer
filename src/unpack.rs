/// Bit-level packing/unpacking for DSL sample data.
///
/// DSL stores samples bit-packed: 1 bit per sample, 8 samples per byte.
/// We unpack to uint8 (each element is 0 or 1) for numpy compatibility.

/// Unpack a bit-packed byte slice into a Vec<u8> where each element is 0 or 1.
///
/// Each byte in `packed` produces 8 output bytes.
/// DSL format is LSB-first: bit 0 = sample 0, bit 1 = sample 1, ...
/// (Matches dsl2sigrok: `blockdata[sample/8] & (1 << (sample % 8))`)
pub fn bit_unpack(packed: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(packed.len() * 8);
    for &byte in packed {
        out.push(byte & 1);
        out.push((byte >> 1) & 1);
        out.push((byte >> 2) & 1);
        out.push((byte >> 3) & 1);
        out.push((byte >> 4) & 1);
        out.push((byte >> 5) & 1);
        out.push((byte >> 6) & 1);
        out.push((byte >> 7) & 1);
    }
    out
}

/// Pack a slice of uint8 (0/1 values) back into bit-packed bytes.
///
/// Every 8 input bytes produce 1 output byte. Input length must be a multiple of 8.
/// LSB-first: sample 0 -> bit 0, sample 1 -> bit 1, ...
pub fn bit_pack(unpacked: &[u8]) -> Vec<u8> {
    assert!(
        unpacked.len() % 8 == 0,
        "bit_pack: input length must be multiple of 8, got {}",
        unpacked.len()
    );
    let mut out = Vec::with_capacity(unpacked.len() / 8);
    for chunk in unpacked.chunks_exact(8) {
        let byte = chunk[0]
            | (chunk[1] << 1)
            | (chunk[2] << 2)
            | (chunk[3] << 3)
            | (chunk[4] << 4)
            | (chunk[5] << 5)
            | (chunk[6] << 6)
            | (chunk[7] << 7);
        out.push(byte);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unpack_one_byte() {
        // LSB-first: 0b10110000 -> bit0=0, bit1=0, .., bit4=1, bit5=1, bit6=0, bit7=1
        // = [0, 0, 0, 0, 1, 1, 0, 1]
        let packed = vec![0b10110000];
        let unpacked = bit_unpack(&packed);
        assert_eq!(unpacked, vec![0, 0, 0, 0, 1, 1, 0, 1]);
    }

    #[test]
    fn test_unpack_all_bits() {
        let packed = vec![0xFF, 0x00, 0xAA]; // 0xAA = 0b10101010
        let unpacked = bit_unpack(&packed);
        assert_eq!(unpacked.len(), 24);
        assert_eq!(&unpacked[0..8], &[1, 1, 1, 1, 1, 1, 1, 1]); // 0xFF -> all 1s
        assert_eq!(&unpacked[8..16], &[0, 0, 0, 0, 0, 0, 0, 0]); // 0x00 -> all 0s
        // 0xAA LSB-first: bit0=0,b1=1,b2=0,b3=1,b4=0,b5=1,b6=0,b7=1
        assert_eq!(&unpacked[16..24], &[0, 1, 0, 1, 0, 1, 0, 1]);
    }

    #[test]
    fn test_round_trip() {
        // Create a 0/1 pattern: alternating 1,0,1,1,0,0,0,1, ...
        let pattern = [1u8, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0];
        let original: Vec<u8> = pattern.repeat(16); // 256 samples, multiple of 8

        let packed = bit_pack(&original);
        let unpacked = bit_unpack(&packed);
        assert_eq!(unpacked, original);
    }

    #[test]
    fn test_pack_simple() {
        // LSB-first: [1,0,1,1,0,0,0,0] -> bit0=1,b1=0,b2=1,b3=1,b4=0,b5=0,b6=0,b7=0
        // = 0b00001101 = 0x0D
        let unpacked = vec![1, 0, 1, 1, 0, 0, 0, 0];
        let packed = bit_pack(&unpacked);
        assert_eq!(packed, vec![0x0D]);
    }
}
