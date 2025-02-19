wheatbelt_rainfall_analyser
==============================

This project aims to gather, analyze, and prepare historical and ongoing rainfall data for integration into a wheat crop forecasting model. The project follows the `cookiecutter-data-science` template for organization and reproducibility.


Project Organization
------------

    ├── LICENSE
    ├── README.md          <- The top-level README for developers using this project.
    ├── data
    │   ├── external       <- Data from third party sources (e.g., gridded rainfall data, shapefiles).
    │   ├── interim        <- Intermediate data that has been transformed.
    │   ├── processed      <- The final, canonical data sets for modeling.
    │   ├── raw            <- The original, immutable data dump.
    │   └── colormaps      <- Color maps for visualisation
    │
    ├── docs               <- A default Sphinx project; see sphinx-doc.org for details
    │
    ├── models             <- Trained and serialized models, model predictions, or model summaries
    │
    ├── notebooks          <- Jupyter notebooks. Naming convention is a number (for ordering),
    │                         the creator's initials, and a short `-` delimited description, e.g.
    │                         `1.0-jqp-initial-data-exploration`.
    │
    ├── references         <- Data dictionaries, manuals, and all other explanatory materials.
    │
    ├── reports            <- Generated analysis as HTML, PDF, LaTeX, etc.
    │   └── figures        <- Generated graphics and figures to be used in reporting
    │
    ├── requirements.txt   <- The requirements file for reproducing the analysis environment, e.g.
    │                         generated with `pip freeze > requirements.txt`
    │
    ├── setup.py           <- makes project pip installable (pip install -e .) so src can be imported
    ├── src                <- Source code for use in this project.
    │   ├── __init__.py    <- Makes src a Python module
    │   │
    │   ├── data           <- Scripts to download or generate data
    │   │   └── download_functions.py
    │   │
    │   ├── features       <- Scripts to turn raw data into features for modeling
    │   │   ├── modify_netcdf.py
    │   │   └── rainfall_functions.py
    │   │
    │   ├── models         <- Scripts to train models and then use trained models to make
    │   │   │                 predictions
    │   │   ├── predict_model.py
    │   │   └── train_model.py
    │   │
    │   └── visualization  <- Scripts to create exploratory and results oriented visualizations
    │       ├── plot_data.py
    │       └── plot_temp.py
    │
    └── node_modules     <- node modules required for puppeteer




Setup
-----
To set up the project environment, run:
`pip install -r requirements.txt`
It is recommended to use a virtual environment (e.g., `venv` or `conda`) to isolate the project dependencies.


Running the analysis
--------------------
1.  Download the data using the scripts in `src/data`.
2.  Explore the data and perform initial analysis using the Jupyter notebooks in the `notebooks` directory.
3.  Generate features from the raw data using the scripts in `src/features`.
4.  Train and evaluate models (implementation pending).


Notebooks
---------
*   Follow the naming convention: `number-initials-description.ipynb` (e.g., `1.0-jqp-initial-data-exploration.ipynb`).
*   Each notebook should have a clear purpose and be well-commented.


--------

<p><small>Project based on the <a target="_blank" href="https://drivendata.github.io/cookiecutter-data-science/">cookiecutter data science project template</a>. #cookiecutterdatascience</small></p>
