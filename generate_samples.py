"""Create the demo source files; does not modify the analytics database."""
from pathlib import Path
from imports import sample
from domain import OPERATORS

if __name__=='__main__':
    target=Path(__file__).resolve().parent/'demo-files'
    target.mkdir(exist_ok=True)
    for operator in OPERATORS:
        for kind in ('inventory','usage','invoice'):
            for extension in ('csv','xlsx'):
                (target/f'demo_{operator}_{kind}.{extension}').write_bytes(sample(operator,kind,extension))
    print(f'Created 18 synthetic source files in {target}')
