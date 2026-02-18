use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn parse_header_items(headers: Vec<String>) -> PyResult<Vec<(String, String)>> {
    let mut parsed: Vec<(String, String)> = Vec::with_capacity(headers.len());

    for header in headers {
        match header.split_once(':') {
            Some((name, value)) => parsed.push((name.trim().to_string(), value.trim_start().to_string())),
            None => {
                return Err(PyValueError::new_err(format!(
                    "Invalid header '{}'. Expected 'name:value'.",
                    header
                )));
            }
        }
    }

    Ok(parsed)
}

#[pyfunction]
fn split_csv_values(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(str::trim)
        .filter(|segment| !segment.is_empty())
        .map(str::to_string)
        .collect()
}

#[pyfunction]
fn parse_request_head(data: &[u8]) -> PyResult<(String, String, String, Vec<(String, String)>)> {
    let decoded = std::str::from_utf8(data)
        .map_err(|_| PyValueError::new_err("Request head is not valid UTF-8/latin-1 byte data"))?;

    let mut lines = decoded.split("\r\n");
    let request_line = lines
        .next()
        .ok_or_else(|| PyValueError::new_err("Missing request line"))?;

    let mut request_parts = request_line.split(' ');
    let method = request_parts
        .next()
        .ok_or_else(|| PyValueError::new_err("Missing HTTP method"))?
        .to_string();
    let target = request_parts
        .next()
        .ok_or_else(|| PyValueError::new_err("Missing request target"))?
        .to_string();
    let version = request_parts
        .next()
        .ok_or_else(|| PyValueError::new_err("Missing HTTP version"))?
        .to_string();

    if request_parts.next().is_some() {
        return Err(PyValueError::new_err("Invalid HTTP request line"));
    }

    let mut headers: Vec<(String, String)> = Vec::new();
    for line in lines {
        if line.is_empty() {
            break;
        }
        match line.split_once(':') {
            Some((name, value)) => headers.push((name.trim().to_string(), value.trim_start().to_string())),
            None => {
                return Err(PyValueError::new_err(format!(
                    "Malformed header line: {}",
                    line
                )));
            }
        }
    }

    Ok((method, target, version, headers))
}

#[pymodule]
fn palfrey_rust(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_header_items, module)?)?;
    module.add_function(wrap_pyfunction!(split_csv_values, module)?)?;
    module.add_function(wrap_pyfunction!(parse_request_head, module)?)?;
    Ok(())
}
