/// DSL file writer: emits .dsl files with cursor annotation channels.
///
/// Copies source data block-by-block and injects extra channels
/// (cursor annotations encoded as bit-packed signals).
use std::io::{Read, Write};

use crate::unpack::bit_pack;

/// Information about how to split extra channel data into blocks.
struct BlockInfo {
    /// Byte size of each block in the source file.
    /// Indexed by block number.
    block_sizes: Vec<u64>,
}

/// Read block sizes from a source .dsl file for probe 0.
///
/// Returns the byte size of each L-0/{block_num} entry.
fn read_block_sizes(path: &str) -> Result<BlockInfo, String> {
    let file = std::fs::File::open(path)
        .map_err(|e| format!("cannot open '{}': {}", path, e))?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| format!("cannot read ZIP: {}", e))?;

    // Use probe 0's blocks as reference
    let mut sizes: Vec<(u64, u64)> = Vec::new(); // (block_num, size)

    for i in 0..archive.len() {
        let entry = archive
            .by_index(i)
            .map_err(|e| format!("entry error: {}", e))?;
        let name = entry.name().to_string();
        if name.starts_with("L-0/") {
            let block_str = &name[4..]; // after "L-0/"
            if let Ok(block_num) = block_str.parse::<u64>() {
                sizes.push((block_num, entry.size()));
            }
        }
    }

    sizes.sort_by_key(|(n, _)| *n);

    // Validate contiguous block numbers starting from 0
    for (i, (block_num, _)) in sizes.iter().enumerate() {
        if *block_num != i as u64 {
            return Err(format!(
                "non-contiguous blocks for probe 0: expected {}, got {}",
                i, block_num
            ));
        }
    }

    Ok(BlockInfo {
        block_sizes: sizes.iter().map(|(_, s)| *s).collect(),
    })
}

/// An extra channel to write into the output .dsl.
pub struct ExtraChannel {
    pub name: String,
    /// Unpacked samples: Vec<u8> where each element is 0 or 1.
    /// Length must equal total_samples.
    pub data: Vec<u8>,
}

/// Write a .dsl file by copying a source .dsl and adding extra channels.
///
/// Uses streaming ZipWriter<File> for bounded memory usage.
pub fn write_dsl(
    source_path: &str,
    output_path: &str,
    extra_channels: &[ExtraChannel],
) -> Result<(), String> {
    // --- 1. Read source header text ---
    let src_file = std::fs::File::open(source_path)
        .map_err(|e| format!("cannot open source: {}", e))?;
    let mut src_archive = zip::ZipArchive::new(src_file)
        .map_err(|e| format!("cannot open source ZIP: {}", e))?;

    let header_text = {
        let mut hf = src_archive
            .by_name("header")
            .map_err(|e| format!("no header in source: {}", e))?;
        let mut text = String::new();
        hf.read_to_string(&mut text)
            .map_err(|e| format!("cannot read header: {}", e))?;
        text
    };

    // --- 2. Compute block sizes from source ---
    let block_info = read_block_sizes(source_path)?;
    let _total_samples_estimate: u64 =
        block_info.block_sizes.iter().map(|s| s * 8).sum();

    // --- 3. Build new header ---
    let total_probes: u16 = header_text
        .lines()
        .find(|l| l.starts_with("total probes ="))
        .and_then(|l| l.split('=').nth(1))
        .and_then(|s| s.trim().parse().ok())
        .ok_or("cannot parse total_probes")?;

    let mut new_header = header_text.clone();
    let original_probe_count = total_probes;
    for (i, ch) in extra_channels.iter().enumerate() {
        let probe_num = original_probe_count + i as u16;
        new_header.push_str(&format!("probe{} = {}\n", probe_num, ch.name));
    }

    // Update total probes count
    let new_total = original_probe_count + extra_channels.len() as u16;
    let old_line = format!("total probes = {}", total_probes);
    let new_line = format!("total probes = {}", new_total);
    new_header = new_header.replace(&old_line, &new_line);

    // --- 4. Write output ZIP ---
    let out_file = std::fs::File::create(output_path)
        .map_err(|e| format!("cannot create output: {}", e))?;
    let mut out_zip = zip::ZipWriter::new(out_file);

    let options =
        zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    // Write updated header
    out_zip
        .start_file("header", options)
        .map_err(|e| format!("cannot write header: {}", e))?;
    out_zip
        .write_all(new_header.as_bytes())
        .map_err(|e| format!("cannot write header data: {}", e))?;

    // Copy all original data blocks and other entries (except header)
    let mut src_file2 = std::fs::File::open(source_path)
        .map_err(|e| format!("cannot reopen source: {}", e))?;

    // Find all L- entry names and their contents
    let mut entries_to_copy: Vec<(String, u64)> = Vec::new();
    {
        let mut archive2 = zip::ZipArchive::new(&mut src_file2)
            .map_err(|e| format!("cannot re-read source ZIP: {}", e))?;
        for i in 0..archive2.len() {
            let entry = archive2
                .by_index(i)
                .map_err(|e| format!("entry error: {}", e))?;
            let name = entry.name().to_string();
            if name.starts_with("L-") {
                entries_to_copy.push((name, entry.size()));
            }
        }
    }

    // Re-open for reading each entry
    {
        // We need a fresh archive for reading entry data
        let src_data = std::fs::read(source_path)
            .map_err(|e| format!("cannot read source: {}", e))?;
        let cursor = std::io::Cursor::new(src_data);
        let mut archive3 = zip::ZipArchive::new(cursor)
            .map_err(|e| format!("cannot open for copy: {}", e))?;

        for (name, _size) in &entries_to_copy {
            let mut buf = Vec::new();
            {
                let mut entry = archive3
                    .by_name(name)
                    .map_err(|e| format!("cannot read entry '{}': {}", name, e))?;
                entry
                    .read_to_end(&mut buf)
                    .map_err(|e| format!("cannot read entry data '{}': {}", name, e))?;
            }

            out_zip
                .start_file(name.as_str(), options)
                .map_err(|e| format!("cannot write entry '{}': {}", name, e))?;
            out_zip
                .write_all(&buf)
                .map_err(|e| format!("cannot write entry data '{}': {}", name, e))?;
        }
    }

    // --- 5. Write extra channel blocks ---
    for (ci, ch) in extra_channels.iter().enumerate() {
        let probe_num = original_probe_count + ci as u16;

        // Bit-pack the extra channel data
        let packed = bit_pack(&ch.data);
        let total_packed_bytes = packed.len() as u64;

        // Split into blocks matching source block sizes
        let mut offset: u64 = 0;
        for (block_num, &block_size) in block_info.block_sizes.iter().enumerate() {
            if offset >= total_packed_bytes {
                break;
            }

            let remaining = total_packed_bytes - offset;
            let chunk_size = block_size.min(remaining);

            let block_name = format!("L-{}/{}", probe_num, block_num);
            out_zip
                .start_file(block_name.as_str(), options)
                .map_err(|e| format!("cannot write cursor block: {}", e))?;

            out_zip
                .write_all(&packed[offset as usize..(offset + chunk_size) as usize])
                .map_err(|e| format!("cannot write cursor block data: {}", e))?;

            offset += chunk_size;
        }
    }

    out_zip
        .finish()
        .map_err(|e| format!("cannot finalize output: {}", e))?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::unpack::bit_unpack;

    fn create_test_dsl(path: &str, probe_data: &[(String, Vec<u8>)]) {
        let n_probes = probe_data.len() as u16;
        let n_samples = probe_data[0].1.len() as u64;
        let _block_size = std::cmp::max(1, (n_samples + 7) / 8);

        let mut header = format!(
            "total probes = {}\nsamplerate = 100 kHz\ntotal samples = {}\ntotal blocks = 1\n",
            n_probes, n_samples
        );
        for (i, (name, _)) in probe_data.iter().enumerate() {
            header.push_str(&format!("probe{} = {}\n", i, name));
        }

        let out_file = std::fs::File::create(path).unwrap();
        let mut zip_w = zip::ZipWriter::new(out_file);
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);

        zip_w.start_file("header", options).unwrap();
        zip_w.write_all(header.as_bytes()).unwrap();

        for (i, (_name, data)) in probe_data.iter().enumerate() {
            let packed = bit_pack(data);
            let name = format!("L-{}/0", i);
            zip_w.start_file(name, options).unwrap();
            zip_w.write_all(&packed).unwrap();
        }

        zip_w.finish().unwrap();
    }

    #[test]
    fn test_write_and_read_back() {
        let dir = std::env::temp_dir().join(format!("dsl_test_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let src_path = dir.join("test.dsl");
        let src_path_str = src_path.to_str().unwrap();
        let out_path = dir.join("out.dsl");
        let out_path_str = out_path.to_str().unwrap();

        // 16 samples, probe 0
        let data: Vec<u8> = vec![0,0,0,1,1,1,1,0,0,0,1,1,1,1,1,0];
        create_test_dsl(src_path_str, &[("tx".into(), data.clone())]);

        // Create an extra channel: cursor positions
        let cursor_data: Vec<u8> = vec![0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0];
        let extra = ExtraChannel {
            name: "_cursor_test".into(),
            data: cursor_data.clone(),
        };

        write_dsl(src_path_str, out_path_str, &[extra]).unwrap();

        // Read back and verify
        let file = std::fs::File::open(out_path_str).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();

        // Check header
        let mut header_text = String::new();
        archive.by_name("header").unwrap().read_to_string(&mut header_text).unwrap();
        assert!(header_text.contains("total probes = 2"));
        assert!(header_text.contains("probe1 = _cursor_test"));

        // Check original data preserved
        let mut buf = Vec::new();
        archive.by_name("L-0/0").unwrap().read_to_end(&mut buf).unwrap();
        let unpacked = bit_unpack(&buf);
        assert_eq!(&unpacked, &data);

        // Check cursor channel
        let mut buf2 = Vec::new();
        archive.by_name("L-1/0").unwrap().read_to_end(&mut buf2).unwrap();
        let unpacked2 = bit_unpack(&buf2);
        assert_eq!(&unpacked2, &cursor_data);

        // Cleanup
        let _ = std::fs::remove_dir_all(&dir);
    }
}
