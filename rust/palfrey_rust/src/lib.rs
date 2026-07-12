use std::borrow::Cow;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

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
fn parse_request_head_normalized<'py>(
    py: Python<'py>,
    data: &[u8],
) -> PyResult<(
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Vec<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)>,
    Option<Bound<'py, PyBytes>>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    bool,
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

    let mut headers: Vec<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)> = Vec::new();
    let mut content_length: Option<Bound<'py, PyBytes>> = None;
    let mut transfer_encoding: Vec<u8> = Vec::new();
    let mut connection: Vec<u8> = Vec::new();
    let mut expect: Vec<u8> = Vec::new();
    let mut upgrade: Vec<u8> = Vec::new();
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
                let lowered_name = ascii_lower(name);
                if lowered_name == b"content-length" {
                    content_length = Some(PyBytes::new_bound(py, value));
                } else if lowered_name == b"transfer-encoding" {
                    transfer_encoding = ascii_lower(value);
                } else if lowered_name == b"connection" {
                    connection = ascii_lower(value);
                } else if lowered_name == b"expect" {
                    expect = ascii_lower(value);
                } else if lowered_name == b"upgrade" {
                    upgrade = ascii_lower(value);
                }
                headers.push((
                    PyBytes::new_bound(py, &lowered_name),
                    PyBytes::new_bound(py, value),
                ));
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

    let websocket_upgrade =
        contains_bytes(&upgrade, b"websocket") && contains_bytes(&connection, b"upgrade");

    Ok((
        PyBytes::new_bound(py, method),
        PyBytes::new_bound(py, target),
        PyBytes::new_bound(py, version),
        headers,
        content_length,
        PyBytes::new_bound(py, &transfer_encoding),
        PyBytes::new_bound(py, &connection),
        PyBytes::new_bound(py, &expect),
        websocket_upgrade,
    ))
}

#[pyfunction]
fn unmask_websocket_payload<'py>(
    py: Python<'py>,
    payload: &[u8],
    masking_key: &[u8],
) -> PyResult<Bound<'py, PyBytes>> {
    if masking_key.len() != 4 {
        return Err(PyValueError::new_err(
            "WebSocket masking key must be exactly 4 bytes",
        ));
    }

    let mut output = Vec::with_capacity(payload.len());
    for (index, byte) in payload.iter().enumerate() {
        output.push(byte ^ masking_key[index & 0b11]);
    }
    Ok(PyBytes::new_bound(py, &output))
}

#[pymodule]
fn palfrey_rust(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_header_items, module)?)?;
    module.add_function(wrap_pyfunction!(split_csv_values, module)?)?;
    module.add_function(wrap_pyfunction!(parse_request_head, module)?)?;
    module.add_function(wrap_pyfunction!(parse_request_head_normalized, module)?)?;
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

fn ascii_lower(input: &[u8]) -> Vec<u8> {
    input.iter().map(|byte| byte.to_ascii_lowercase()).collect()
}

fn contains_bytes(haystack: &[u8], needle: &[u8]) -> bool {
    if needle.is_empty() {
        return true;
    }
    haystack
        .windows(needle.len())
        .any(|window| window == needle)
}
