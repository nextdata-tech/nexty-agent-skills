# Data product structure
Data products are a folder containing specific files defining the interface and behavior of the data product, for example:

```
data-product-name
├── .nxdignore
├── contracts
│   ├── expectation.py
│   └── promise.py
├── docs
│   └── readme.md
├── models.py
├── requirements.txt
├── spec.py
└── transform.py
```

This is an example of a data product performing a transformation (transform.py) in Python. Note that SQL transforms are also supported. The transform and all other aspect of the data product are specified using the Nextdata Python DSL, which is typically defined the spec.py Python module. This data product also supports custom verification of inputs and outputs via `expectation.py` and `promise.py` Python modules which specify data contracts. Custom verification may also utilize supported tools, such as Monte Carlo.

The key files are:

* `.nxdignore`: specify files and directories to exclude from the data product bundle when building and deploying.
* `models.py`: specify the various models and their attributes for validation by the mesh.
* `requirements.txt`: specify the Python dependencies required by the data product, which will be installed in the data product's execution environment.
* `spec.py`: specifies the data product identifiers, transform logic, inputs and outputs, semantic models, contracts, access policies and more.
* `transform.py`: defines the transformation code of the data product.

For a more detailed definition of the interfaces of the various Python modules and supporting API and libraries, see the Python Data Product Spec DSL.