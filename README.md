# GRASS as a Geocomputational Engine

![GitHub License](https://img.shields.io/github/license/baharmon/grass-as-a-geocomputational-engine)

This repository contains supplemental material for the paper GRASS as a Geocomputational Engine. 

## Notebooks

| Case Study                | Notebook                        | Dataset                                 |
| ------------------------- | ------------------------------- | --------------------------------------- |
| Basic usage               | basics.ipynb                    |                                         |
| Lidar segmentation        | lidar.ipynb                     | https://doi.org/10.5281/zenodo.24535069 |
| Species diversity         | diversity.ipynb                 | https://doi.org/10.17605/OSF.IO/UC6DA   |
| Exploratory data analysis | exploratory-data-analysis.ipynb | https://doi.org/10.5281/zenodo.24457872 |
| Stream bank extraction    | stream-bank-extraction.ipynb    | https://doi.org/10.5281/zenodo.23600244 |

## Usage

Create an environment with the dependencies, activate the environment, and then run a notebook:

#### Conda
```bash
conda env create --file environment.yml
conda activate grass-engine
jupyter lab basics.ipynb
```

#### Pixi
```bash
pixi install
pixi run jupyter lab basics.ipynb
```

## License

This project is licensed under the GNU General Public License v3.0 or later.