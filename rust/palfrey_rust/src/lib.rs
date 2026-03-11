use std::borrow::Cow;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn parse_header_items(headers: Vec<String>) -> PyResult<Vec<(String, String)>> {
    let mut parsed: Vec<(String, String)> = Vec::with_capacity(headers.len());

    for header in headers {
        match header.split_once(':') {
            Some((name, value)) => {
                parsed.push((name.trim().to_string(), value.trim_start().to_string()))
            }
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
fn parse_request_head<'a>(
    data: &'a [u8],
) -> PyResult<(
    Cow<'a, [u8]>,
    Cow<'a, [u8]>,
    Cow<'a, [u8]>,
    Vec<(Cow<'a, [u8]>, Cow<'a, [u8]>)>,
)> {
    let request_line_end = data
        .windows(2)
        .position(|window| window == b"\r\n")
        .ok_or_else(|| PyValueError::new_err("Missing request line"))?;

    let request_line = &data[..request_line_end];
    if request_line.is_empty() {
        return Err(PyValueError::new_err("Missing request line"));
    }

    let mut request_parts = request_line.splitn(3, |byte| *byte == b' ');
    let method = request_parts
        .next()
        .ok_or_else(|| PyValueError::new_err("Invalid request line"))?;
    let target = request_parts
        .next()
        .ok_or_else(|| PyValueError::new_err("Invalid request line"))?;
    let version = request_parts
        .next()
        .ok_or_else(|| PyValueError::new_err("Invalid request line"))?;

    if method.is_empty() || target.is_empty() || version.is_empty() || version.contains(&b' ') {
        return Err(PyValueError::new_err("Invalid request line"));
    }

    let mut headers: Vec<(Cow<'a, [u8]>, Cow<'a, [u8]>)> = Vec::new();
    let mut cursor = request_line_end + 2;

    while cursor <= data.len() {
        let line_end = match data[cursor..]
            .windows(2)
            .position(|window| window == b"\r\n")
        {
            Some(position) => cursor + position,
            None => data.len(),
        };
        let line = &data[cursor..line_end];

        if line.is_empty() {
            break;
        }

        match line.iter().position(|byte| *byte == b':') {
            Some(index) => {
                let name = trim_ascii_whitespace(&line[..index]);
                let value = trim_ascii_whitespace_start(&line[index + 1..]);
                headers.push((Cow::Borrowed(name), Cow::Borrowed(value)));
            }
            None => {
                return Err(PyValueError::new_err(format!(
                    "Malformed header line: {}",
                    String::from_utf8_lossy(line)
                )));
            }
        }

        if line_end == data.len() {
            break;
        }
        cursor = line_end + 2;
    }

    Ok((
        Cow::Borrowed(method),
        Cow::Borrowed(target),
        Cow::Borrowed(version),
        headers,
    ))
}

#[pyfunction]
fn unmask_websocket_payload(payload: &[u8], masking_key: &[u8]) -> PyResult<Vec<u8>> {
    if masking_key.len() != 4 {
        return Err(PyValueError::new_err(
            "WebSocket masking key must be exactly 4 bytes",
        ));
    }

    let mut output = Vec::with_capacity(payload.len());
    for (index, byte) in payload.iter().enumerate() {
        output.push(byte ^ masking_key[index & 0b11]);
    }
    Ok(output)
}

#[pymodule]
fn palfrey_rust(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_header_items, module)?)?;
    module.add_function(wrap_pyfunction!(split_csv_values, module)?)?;
    module.add_function(wrap_pyfunction!(parse_request_head, module)?)?;
    module.add_function(wrap_pyfunction!(unmask_websocket_payload, module)?)?;
    Ok(())
}

fn trim_ascii_whitespace(input: &[u8]) -> &[u8] {
    let start = input
        .iter()
        .position(|byte| !byte.is_ascii_whitespace())
        .unwrap_or(input.len());
    let end = input
        .iter()
        .rposition(|byte| !byte.is_ascii_whitespace())
        .map_or(start, |index| index + 1);
    &input[start..end]
}

fn trim_ascii_whitespace_start(input: &[u8]) -> &[u8] {
    let start = input
        .iter()
        .position(|byte| !byte.is_ascii_whitespace())
        .unwrap_or(input.len());
    &input[start..]
}
