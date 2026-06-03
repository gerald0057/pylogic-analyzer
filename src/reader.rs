/// ZIP-based DSL file reader.
///
/// Reads a .dsl file (ZIP archive) and extracts header + channel data.
use std::collections::HashMap;
use std::io::Read;

use crate::header::parse_header;
use crate::types::DslHeader;
use crate::unpack::bit_unpack;

/// Identifies a data block within the .dsl ZIP.
#[derive(Debug, Clone)]
struct BlockEntry {
    block_num: u64,
    zip_index: usize,
}

pub struct DslReader {
    header: DslHeader,
    block_map: HashMap<u16, Vec<BlockEntry>>,
    // We don't hold the zip archive open between calls;
    // instead we reopen and seek by zip_index on each read.
    path: String,
}

impl DslReader {
    /// Open a .dsl file, parse its header, and index all data blocks.
    pub fn open(path: &str) -> Result<Self, String> {
        let file = std::fs::File::open(path)
            .map_err(|e| format!("cannot open '{}': {}", path, e))?;

        let mut archive = zip::ZipArchive::new(file)
            .map_err(|e| format!("cannot read ZIP '{}': {}", path, e))?;

        // Read header
        let header_text = {
            let mut hf = archive
                .by_name("header")
                .map_err(|e| format!("no 'header' entry in '{}': {}", path, e))?;
            let mut text = String::new();
            hf.read_to_string(&mut text)
                .map_err(|e| format!("failed to read header: {}", e))?;
            text
        };

        let header = parse_header(&header_text)?;

        // Index all data blocks: L-{probe}/{block_num}
        let mut block_map: HashMap<u16, Vec<BlockEntry>> = HashMap::new();

        for i in 0..archive.len() {
            let entry = archive
                .by_index(i)
                .map_err(|e| format!("failed to get entry {}: {}", i, e))?;
            let name = entry.name().to_string();

            // Match L-{probe}/{block_num} pattern
            if let Some(rest) = name.strip_prefix("L-") {
                if let Some(slash_pos) = rest.find('/') {
                    let probe_str = &rest[..slash_pos];
                    let block_str = &rest[slash_pos + 1..];
                    if let (Ok(probe), Ok(block_num)) =
                        (probe_str.parse::<u16>(), block_str.parse::<u64>())
                    {
                        block_map.entry(probe).or_default().push(BlockEntry {
                            block_num,
                            zip_index: i,
                        });
                    }
                }
            }
        }

        // Sort blocks by block_num within each probe
        for blocks in block_map.values_mut() {
            blocks.sort_by_key(|b| b.block_num);
        }

        Ok(Self {
            header,
            block_map,
            path: path.to_string(),
        })
    }

    /// Return a copy of the parsed header.
    pub fn header(&self) -> DslHeader {
        self.header.clone()
    }

    /// Read all block data for a probe, concatenate, and bit-unpack.
    ///
    /// Returns a Vec<u8> where each element is 0 or 1.
    /// The length should equal total_samples (if blocks are complete).
    pub fn read_channel(&self, probe: u16) -> Result<Vec<u8>, String> {
        let blocks = self
            .block_map
            .get(&probe)
            .ok_or_else(|| format!("probe {} not found in .dsl file", probe))?;

        let file = std::fs::File::open(&self.path)
            .map_err(|e| format!("cannot reopen '{}': {}", self.path, e))?;

        let mut archive = zip::ZipArchive::new(file)
            .map_err(|e| format!("cannot re-read ZIP: {}", e))?;

        let mut packed = Vec::new();

        for block in blocks {
            let mut entry = archive
                .by_index(block.zip_index)
                .map_err(|e| format!("failed to read block L-{}/{}: {}", probe, block.block_num, e))?;
            let mut buf = Vec::new();
            entry
                .read_to_end(&mut buf)
                .map_err(|e| format!("failed to read block data: {}", e))?;
            packed.extend_from_slice(&buf);
        }

        let mut unpacked = bit_unpack(&packed);

        // Truncate to total_samples (last block may have padding)
        let total = self.header.total_samples as usize;
        if unpacked.len() > total {
            unpacked.truncate(total);
        }

        Ok(unpacked)
    }

    /// Return the number of probes listed in the header.
    pub fn probe_count(&self) -> u16 {
        self.header.total_probes
    }
}
