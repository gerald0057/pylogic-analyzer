/// Parse the `header` text entry from a .dsl ZIP file.
use crate::types::{parse_samplerate, DslHeader};

/// Parse the header text content into a DslHeader struct.
///
/// The header format (from dsl2sigrok analysis):
/// ```
/// total probes = 12
/// samplerate = 25 MHz
/// total samples = 1400000
/// total blocks = 500
/// probe0 = tx
/// probe1 = sync win
/// ...
/// ```
pub fn parse_header(text: &str) -> Result<DslHeader, String> {
    let mut total_probes: Option<u16> = None;
    let mut samplerate: Option<f64> = None;
    let mut total_samples: Option<u64> = None;
    let mut total_blocks: Option<u64> = None;
    let mut probe_names: Vec<(u16, String)> = Vec::new();

    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        if let Some(rest) = line.strip_prefix("total probes = ") {
            total_probes = Some(
                rest.trim()
                    .parse()
                    .map_err(|_| format!("invalid total probes: '{}'", rest))?,
            );
        } else if let Some(rest) = line.strip_prefix("samplerate = ") {
            samplerate = Some(parse_samplerate(rest)?);
        } else if let Some(rest) = line.strip_prefix("total samples = ") {
            total_samples = Some(
                rest.trim()
                    .parse()
                    .map_err(|_| format!("invalid total samples: '{}'", rest))?,
            );
        } else if let Some(rest) = line.strip_prefix("total blocks = ") {
            total_blocks = Some(
                rest.trim()
                    .parse()
                    .map_err(|_| format!("invalid total blocks: '{}'", rest))?,
            );
        } else if let Some(rest) = line.strip_prefix("probe") {
            let rest = rest.trim();
            if let Some(eq_pos) = rest.find('=') {
                let probe_num: u16 = rest[..eq_pos]
                    .trim()
                    .parse()
                    .map_err(|_| format!("invalid probe number in '{}'", line))?;

                // Handle probe names with trailing spaces after "probeNUM = "
                // The name is everything after '=' trimmed, which may contain spaces
                let name_start = eq_pos + 1;
                let name = rest[name_start..].trim().to_string();
                probe_names.push((probe_num, name));
            }
        }
    }

    let total_probes = total_probes.ok_or("missing 'total probes'")?;
    let samplerate = samplerate.ok_or("missing 'samplerate'")?;
    let total_samples = total_samples.ok_or("missing 'total samples'")?;
    let total_blocks = total_blocks.ok_or("missing 'total blocks'")?;

    // Build ordered probe name list, matching dsl2sigrok behavior:
    // probe_names vector is indexed by probe number.
    let max_probe = probe_names
        .iter()
        .map(|(n, _)| *n)
        .max()
        .unwrap_or(total_probes.saturating_sub(1));

    let mut names: Vec<String> = vec![String::new(); (max_probe as usize) + 1];
    for (num, name) in probe_names {
        names[num as usize] = name;
    }

    Ok(DslHeader {
        total_probes,
        samplerate,
        total_samples,
        total_blocks,
        probe_names: names,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_basic_header() {
        let text = "total probes = 2\n\
                    samplerate = 25 MHz\n\
                    total samples = 1000\n\
                    total blocks = 5\n\
                    probe0 = tx\n\
                    probe1 = rx\n";
        let h = parse_header(text).unwrap();
        assert_eq!(h.total_probes, 2);
        assert!((h.samplerate - 25_000_000.0).abs() < 1.0);
        assert_eq!(h.total_samples, 1000);
        assert_eq!(h.total_blocks, 5);
        assert_eq!(h.probe_names.len(), 2);
        assert_eq!(h.probe_names[0], "tx");
        assert_eq!(h.probe_names[1], "rx");
    }

    #[test]
    fn test_parse_header_with_spaces_in_names() {
        let text = "total probes = 3\n\
                    samplerate = 25 MHz\n\
                    total samples = 1000\n\
                    total blocks = 5\n\
                    probe0 = sync win\n\
                    probe1 = sync pul\n\
                    probe2 = tx\n";
        let h = parse_header(text).unwrap();
        assert_eq!(h.probe_names[0], "sync win");
        assert_eq!(h.probe_names[1], "sync pul");
        assert_eq!(h.probe_names[2], "tx");
    }

    #[test]
    fn test_missing_fields() {
        assert!(parse_header("total probes = 2").is_err());
    }
}
