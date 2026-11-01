# Reproducibility check - full, seed 20261022

Generated the dataset twice in separate folders with the same seed. **All files identical** (58 files compared by row count and SHA-256).

Shipped copy (`data/full`): **identical**: every file matches run 1, both by the SHA-256 listed in `manifest.json` and by the bytes on disk.

Environment: Python 3.14.4 on Windows-11.

| File | Rows | SHA-256 (run 1) | Same in run 2 | Same as shipped |
|---|---:|---|:-:|:-:|
| csv/approval.csv | 1978 | `cb74aac516f587d1...` | yes | yes |
| csv/budget.csv | 33 | `132dffb6ed71126f...` | yes | yes |
| csv/budget_balance.csv | 33 | `584dddb7f0e03be4...` | yes | yes |
| csv/budget_transaction.csv | 3808 | `5dfec40b810b0bbb...` | yes | yes |
| csv/delivery.csv | 1076 | `bb85781b92666bae...` | yes | yes |
| csv/delivery_line.csv | 2049 | `04b2c3f79847d850...` | yes | yes |
| csv/department.csv | 16 | `9b1283f58e7e9fad...` | yes | yes |
| csv/exception_register.csv | 954 | `693d2eadfbe9919b...` | yes | yes |
| csv/fx_rate.csv | 84 | `f3e8599de9a7ba9d...` | yes | yes |
| csv/item.csv | 172 | `38c7b30b2339e42f...` | yes | yes |
| csv/item_category.csv | 14 | `e0f3f93bb3412b6b...` | yes | yes |
| csv/po_line.csv | 1841 | `89b456f6bdecad3b...` | yes | yes |
| csv/purchase_order.csv | 918 | `3def191b4a86c420...` | yes | yes |
| csv/purchase_request.csv | 1200 | `21c704bd241c293e...` | yes | yes |
| csv/quote_evaluation.csv | 1404 | `242601dc906ff5e7...` | yes | yes |
| csv/quote_line.csv | 2665 | `5c9e9fcde10479ed...` | yes | yes |
| csv/request_line.csv | 2195 | `a41a4e40b5b99ee4...` | yes | yes |
| csv/requester.csv | 300 | `4ef087c88adedebb...` | yes | yes |
| csv/rfq.csv | 500 | `47cd4690e6c0f08c...` | yes | yes |
| csv/rfq_award.csv | 455 | `37be6f7bf7c4a28c...` | yes | yes |
| csv/rfq_supplier.csv | 2354 | `2333cb29ede4bad5...` | yes | yes |
| csv/status_event.csv | 13479 | `5c8a40dee2708b72...` | yes | yes |
| csv/supplier.csv | 120 | `0bbdaae71e6164fb...` | yes | yes |
| csv/supplier_category.csv | 210 | `7ab9e03603de1fb6...` | yes | yes |
| csv/supplier_quote.csv | 1500 | `6d30bea1bd4ea031...` | yes | yes |
| csv/supplier_risk_flag.csv | 41 | `8bc718890739d7de...` | yes | yes |
| csv/supplier_status_history.csv | 141 | `a33950771b99f730...` | yes | yes |
| ground_truth/ground_truth.csv | 65 | `c9dd3f170df20891...` | yes | yes |
| ground_truth/ground_truth.json | 65 | `c60c059117b82992...` | yes | yes |
| json/approval.json | 1978 | `f72414d0a1e454b8...` | yes | yes |
| json/budget.json | 33 | `d5492e19ae8971ee...` | yes | yes |
| json/budget_balance.json | 33 | `fbfa0f85375b7345...` | yes | yes |
| json/budget_transaction.json | 3808 | `0e23defb770c04c8...` | yes | yes |
| json/delivery.json | 1076 | `ec9975754fee9a3f...` | yes | yes |
| json/delivery_line.json | 2049 | `f53cdf72aee40fdd...` | yes | yes |
| json/department.json | 16 | `7443f662136780f2...` | yes | yes |
| json/exception_register.json | 954 | `72478755411f2946...` | yes | yes |
| json/fx_rate.json | 84 | `41cb7f2054a30eeb...` | yes | yes |
| json/item.json | 172 | `c32eebb9ef1b78f2...` | yes | yes |
| json/item_category.json | 14 | `f7bd4898885421da...` | yes | yes |
| json/po_line.json | 1841 | `b7c28838304034f8...` | yes | yes |
| json/purchase_order.json | 918 | `315a4a902c353627...` | yes | yes |
| json/purchase_request.json | 1200 | `4ecfe6140f1ba11b...` | yes | yes |
| json/quote_evaluation.json | 1404 | `17a37b35e8a43122...` | yes | yes |
| json/quote_line.json | 2665 | `a30116151814d3f9...` | yes | yes |
| json/request_line.json | 2195 | `3e34bdf67cb4e73e...` | yes | yes |
| json/requester.json | 300 | `99d6a0666ba4aa05...` | yes | yes |
| json/rfq.json | 500 | `544615782b5470cc...` | yes | yes |
| json/rfq_award.json | 455 | `5b4bdc4e5bce4122...` | yes | yes |
| json/rfq_supplier.json | 2354 | `fa760f926af0e54f...` | yes | yes |
| json/status_event.json | 13479 | `e79f32d6c71e7dc6...` | yes | yes |
| json/supplier.json | 120 | `09f019707f2e6279...` | yes | yes |
| json/supplier_category.json | 210 | `a727a6e5b04ce35f...` | yes | yes |
| json/supplier_quote.json | 1500 | `1904f48f48a50c8c...` | yes | yes |
| json/supplier_risk_flag.json | 41 | `c2a93857e10e6465...` | yes | yes |
| json/supplier_status_history.json | 141 | `3ac4080a4fa23da5...` | yes | yes |
| sql/schema.sql |  | `5200968179a253d3...` | yes | yes |
| sql/seed.sql | 39540 | `47d60b697c68378e...` | yes | yes |
