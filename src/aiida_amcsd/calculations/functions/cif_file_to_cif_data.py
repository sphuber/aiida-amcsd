# -*- coding: utf-8 -*-
"""Calcfunction to transform a ``SinglefileData`` containing a CIF file into a ``CifData`` node.

The function contains a number of regex substitutions if the creation of the ``CifData`` from the CIF file content fails
which are explicitly added for files stored in the AMCSD. These are mostly unimportant syntax mistakes in the
publication information that should not affect the quality of the crystallographical information.
"""
from aiida.engine import calcfunction
from aiida.orm import CifData, SinglefileData


@calcfunction
def cif_file_to_cif_data(cif_file: SinglefileData) -> CifData:
    """Convert a CIF file in the form of a ``SinglefileData`` into a ``CifData`` node."""
    import contextlib
    import io
    import re

    from CifFile.StarFile import StarError

    substitutions = [
        (r'\r\n', '\n'),  # CRLF of Windows
        (r'\r', '\n'),  # CRLF of Mac
        (r'.*; doi:.*\n', '\n'),  # Extraneous DOI
        (r'.*DOI:.*\n', '\n'),  # Extraneous DOI
        (r'(\_journal_volume)[ ]*\n', r'\1 0\n'),  # Missing volume number
        (r'(\_journal_page_first)[ ]*\n', r'\1 0\n'),  # Missing first page
        (r'(\_journal_page_last)[ ]*\n', r'\1 0\n'),  # Missing last page
        (r'(\_journal_page_first)\s*[A-Za-z0-9]*\s([0-9]*)\n', r'\1 \2\n'),  # Extraneous characters before page number
        (r'(\_journal_page_last)[ ]*(?=.*[0-9])(?=.*[a-zA-Z])(.*)\n', r'\1 0\n'),  # Value contains alpha characters
    ]

    try:
        with cif_file.open() as handle:
            with contextlib.redirect_stderr(io.StringIO()):
                cif_data = CifData(file=handle)
    except StarError as exception:

        content = cif_file.get_content()
        modifications = []

        for pattern, replacement in substitutions:

            modified = re.sub(pattern, replacement, content)

            if modified != content:
                modifications.append(pattern)
                content = modified

            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    cif_data = CifData(file=io.BytesIO(content.encode('utf-8')))
            except StarError:
                continue
            else:
                cif_data.set_attribute('modifications', modifications)
                break

        else:
            raise ValueError(f'failed to parse {cif_file}') from exception

    return {'cif_data': cif_data}
