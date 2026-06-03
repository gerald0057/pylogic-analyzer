/// PyO3 native module for DSL file parsing and writing.
///
/// Exposes `DslReader` and `DslWriter` as Python classes via maturin.
use numpy::PyArray1;
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};

mod header;
mod reader;
mod types;
mod unpack;
mod writer;

use reader::DslReader;
use writer::{write_dsl, ExtraChannel};

/// Python-facing DSL reader.
#[pyclass(name = "DslReader")]
struct PyDslReader {
    inner: DslReader,
}

#[pymethods]
impl PyDslReader {
    #[staticmethod]
    fn open(path: &str) -> PyResult<Self> {
        let inner = DslReader::open(path).map_err(|e| PyIOError::new_err(e))?;
        Ok(Self { inner })
    }

    fn get_header<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let h = self.inner.header();
        let dict = PyDict::new(py);
        dict.set_item("total_probes", h.total_probes)?;
        dict.set_item("samplerate", h.samplerate)?;
        dict.set_item("total_samples", h.total_samples)?;
        dict.set_item("total_blocks", h.total_blocks)?;
        dict.set_item("probe_names", h.probe_names)?;
        Ok(dict)
    }

    fn read_channel<'py>(
        &mut self,
        py: Python<'py>,
        probe: u16,
    ) -> PyResult<Bound<'py, PyArray1<u8>>> {
        let data = self
            .inner
            .read_channel(probe)
            .map_err(|e| PyIOError::new_err(e))?;
        Ok(PyArray1::from_vec(py, data))
    }

    fn probe_count(&self) -> u16 {
        self.inner.probe_count()
    }

    fn total_samples(&self) -> u64 {
        self.inner.header().total_samples
    }

    fn samplerate(&self) -> f64 {
        self.inner.header().samplerate
    }

    fn probe_names(&self) -> Vec<String> {
        self.inner.header().probe_names.clone()
    }
}

/// Python-facing DSL writer.
///
/// Writes a .dsl file by copying source data and adding cursor annotation channels.
#[pyclass(name = "DslWriter")]
struct PyDslWriter;

#[pymethods]
impl PyDslWriter {
    /// Write a .dsl output file.
    ///
    /// Args:
    ///     source_path (str): Path to the source .dsl file.
    ///     output_path (str): Path to write the output .dsl.
    ///     extra_channels (list[tuple[str, bytes]]): List of (name, numpy_array)
    ///         where numpy_array is a uint8 array (0/1 values).
    #[staticmethod]
    fn write(
        source_path: &str,
        output_path: &str,
        extra_channels: Bound<'_, PyList>,
    ) -> PyResult<()> {
        let mut channels: Vec<ExtraChannel> = Vec::new();

        for item in extra_channels.iter() {
            let tuple = item.downcast::<PyTuple>()?;
            let name: String = tuple.get_item(0)?.extract()?;
            let array = tuple.get_item(1)?;

            // Extract numpy array as Vec<u8>
            let data: Vec<u8> = Python::with_gil(|_py| {
                let arr = array.call_method0("tobytes")?;
                let bytes = arr.downcast::<PyBytes>()?;
                Ok::<Vec<u8>, PyErr>(bytes.as_bytes().to_vec())
            })?;

            channels.push(ExtraChannel { name, data });
        }

        write_dsl(source_path, output_path, &channels)
            .map_err(|e| PyIOError::new_err(e))?;

        Ok(())
    }
}

/// Python module entry point.
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyDslReader>()?;
    m.add_class::<PyDslWriter>()?;
    Ok(())
}
