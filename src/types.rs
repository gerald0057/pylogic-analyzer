/// Shared types for DSL file parsing.
///
/// The DSL format is a ZIP archive containing a text header and
/// bit-packed binary data blocks per probe.

/// Parsed metadata from the `header` entry in a .dsl ZIP file.
#[derive(Debug, Clone)]
pub struct DslHeader {
    pub total_probes: u16,
    pub samplerate: f64, // samples per second (Hz)
    pub total_samples: u64,
    pub total_blocks: u64, // blocks per probe
    pub probe_names: Vec<String>,
}

/// Parse a samplerate string into Hz.
///
/// Supported formats: "25 MHz", "100 kHz", "1 GHz", "1 kHz"
pub fn parse_samplerate(s: &str) -> Result<f64, String> {
    let s = s.trim();
    if s.is_empty() {
        return Err("empty samplerate string".into());
    }

    let (value_str, unit) = if let Some(pos) = s.find(|c: char| !c.is_ascii_digit() && c != '.') {
        let (v, u) = s.split_at(pos);
        (v.trim(), u.trim().to_lowercase())
    } else {
        (s, String::from("hz"))
    };

    let value: f64 = value_str
        .parse()
        .map_err(|e| format!("invalid samplerate value '{}': {}", value_str, e))?;

    let multiplier = match unit.as_str() {
        "hz" | "" => 1.0,
        "khz" => 1_000.0,
        "mhz" => 1_000_000.0,
        "ghz" => 1_000_000_000.0,
        _ => return Err(format!("unknown samplerate unit '{}'", unit)),
    };

    Ok(value * multiplier)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_samplerate() {
        assert!((parse_samplerate("25 MHz").unwrap() - 25_000_000.0).abs() < 1.0);
        assert!((parse_samplerate("100 kHz").unwrap() - 100_000.0).abs() < 1.0);
        assert!((parse_samplerate("1 GHz").unwrap() - 1_000_000_000.0).abs() < 1.0);
        assert!((parse_samplerate("1 kHz").unwrap() - 1_000.0).abs() < 1.0);
        assert!((parse_samplerate("1000").unwrap() - 1_000.0).abs() < 1.0);
        assert!(parse_samplerate("").is_err());
    }
}
