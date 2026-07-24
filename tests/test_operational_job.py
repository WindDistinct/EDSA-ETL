import pandas as pd

from application.jobs.operational_job import OperationalJob


def _write_operational_file(path) -> None:

    ida = pd.DataFrame(
        {
            "FECHA": ["2026-07-06"],
            "HORA": ["08:00:00"],
            "PLACA": ["A0P736"],
            "CONDUCTOR": ["Juan Perez, 12345678"],
            "HORA_REAL_ULTIMO_PUNTO": [
                "Mon Jul 06 2026 18:00:00 GMT-0500 (hora estándar de Perú)"
            ],
            "HORA_CALCULADA_ULTIMO_PUNTO": [
                "Mon Jul 06 2026 18:30:00 GMT-0500 (hora estándar de Perú)"
            ],
        }
    )

    vuelta = pd.DataFrame(
        {
            "FECHA": ["2026-07-06"],
            "HORA": ["19:00:00"],
            "PLACA": ["A0P736"],
            "CONDUCTOR": ["Juan Perez, 12345678"],
            "HORA_REAL_ULTIMO_PUNTO": [
                "Mon Jul 06 2026 23:00:00 GMT-0500 (hora estándar del Perú)"
            ],
            "HORA_CALCULADA_ULTIMO_PUNTO": [""],
        }
    )

    with pd.ExcelWriter(path) as writer:
        ida.to_excel(writer, sheet_name="Ida", index=False)
        vuelta.to_excel(writer, sheet_name="Vuelta", index=False)


def _write_clean_file(path) -> None:

    df = pd.DataFrame(
        {
            "RUC_EMPRESA": ["20123456789"],
            "CODIGO_RUTA": ["R1"],
            "PLACA": ["A0P736"],
            "IMEI": ["863238075031916"],
        }
    )

    df.to_excel(path, index=False)


def test_operational_job_merges_and_produces_expected_columns(tmp_path):

    operational_file = tmp_path / "operational.xlsx"
    clean_file = tmp_path / "clean.xlsx"
    output_file = tmp_path / "output.xlsx"

    _write_operational_file(operational_file)
    _write_clean_file(clean_file)

    OperationalJob().run(
        str(operational_file),
        str(clean_file),
        str(output_file),
    )

    result = pd.read_excel(output_file, dtype=str)

    assert list(result.columns) == OperationalJob.OUTPUT_COLUMNS
    assert len(result) == 2
    assert (result["PLACA"] == "A0P736").all()
    assert (result["RUC_EMPRESA"] == "20123456789").all()
    assert (result["CODIGO_RUTA"] == "R1").all()
    assert (result["NRO_DOC_CONDUCTOR"] == "12345678").all()
    assert set(result["SENTIDO"].astype(str)) == {"0", "1"}
