/// Parse the `header` text entry from a .dsl ZIP file.
use crate::types::{parse_samplerate, DslHeader};

/// Parse the header text content into a DslHeader struct.
///
/// Supports two formats:
/// 1. INI-style (DSView >= 3):
///    ```
///    [version]
///    version = 3
///    [header]
///    driver = DSLogic
///    total probes = 12
///    samplerate = 25 MHz
///    total samples = 1400000
///    total blocks = 500
///    probe0 = tx
///    probe1 = sync win
///    ...
///    ```
/// 2. Flat key=value (legacy / dsl2sigrok):
///    ```
///    total probes = 12
///    samplerate = 25 MHz
///    total samples = 1400000
///    total blocks = 500
///    probe0 = tx
///    probe1 = sync win
///    ...
///    ```
pub fn parse_header(text: &str) -> Result<DslHeader, String> {
    let mut total_probes: Option<u16> = None;
    let mut samplerate: Option<f64> = None;
    let mut total_samples: Option<u64> = None;
    let mut total_blocks: Option<u64> = None;
    let mut probe_names: Vec<(u16, String)> = Vec::new();

    // Track which section we're in. In INI-style, only [header] fields matter.
    // In flat format, all lines are implicitly in [header].
    let mut in_header_section = true; // default for flat format
    let has_sections = text.contains('[');

    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        // Handle section markers
        if has_sections && line.starts_with('[') && line.ends_with(']') {
            let section = &line[1..line.len() - 1].trim().to_lowercase();
            in_header_section = section == "header";
            continue;
        }

        // If we're not in [header] section of INI format, skip
        if !in_header_section {
            continue;
        }

        // Parse key = value within current section
        if let Some((key, value)) = parse_key_value(line) {
            match key {
                "total probes" => {
                    total_probes = Some(
                        value
                            .parse()
                            .map_err(|_| format!("invalid total probes: '{}'", value))?,
                    );
                }
                "samplerate" => {
                    samplerate = Some(parse_samplerate(value)?);
                }
                "total samples" => {
                    total_samples = Some(
                        value
                            .parse()
                            .map_err(|_| format!("invalid total samples: '{}'", value))?,
                    );
                }
                "total blocks" => {
                    total_blocks = Some(
                        value
                            .parse()
                            .map_err(|_| format!("invalid total blocks: '{}'", value))?,
                    );
                }
                _ => {
                    // Maybe a probe line: "probeN = name"
                    if let Some(rest) = key.strip_prefix("probe") {
                        if let Ok(probe_num) = rest.trim().parse::<u16>() {
                            probe_names.push((probe_num, value.to_string()));
                        }
                    }
                    // Ignore other fields (driver, device mode, trigger time, etc.)
                }
            }
        }
    }

    let total_probes = total_probes.ok_or("missing 'total probes'")?;
    let samplerate = samplerate.ok_or("missing 'samplerate'")?;
    let total_samples = total_samples.ok_or("missing 'total samples'")?;
    let total_blocks = total_blocks.ok_or("missing 'total blocks'")?;

    // Build ordered probe name list, indexed by probe number.
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

/// Parse a "key = value" line, returning (key, value) or None.
fn parse_key_value(line: &str) -> Option<(&str, &str)> {
    let eq_pos = line.find('=')?;
    let key = line[..eq_pos].trim();
    let value = line[eq_pos + 1..].trim();
    if key.is_empty() {
        return None;
    }
    Some((key, value))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_flat_header() {
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
    fn test_parse_ini_header() {
        let text = "[version]\n\
                    version = 3\n\
                    [header]\n\
                    driver = DSLogic\n\
                    device mode = 0\n\
                    capturefile = data\n\
                    total samples = 1000\n\
                    total probes = 2\n\
                    total blocks = 5\n\
                    samplerate = 25 MHz\n\
                    trigger time = 12345\n\
                    trigger pos = 0\n\
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
        let text = "[header]\n\
                    total probes = 3\n\
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
