# AgriSense

A browser-based Streamlit prototype for exploring crop and tree suitability at one location in Pakistan.

## Run on Windows

1. Extract the entire ZIP to a writable folder on the Windows PC.
2. Install 64-bit Python 3.12 if needed. Enable **Add Python to PATH** during installation.
3. Double-click **Start AgriSense.bat**. The first run downloads dependencies and creates a local environment in the extracted folder.
4. Keep the launcher window open. If the browser does not open automatically, go to http://localhost:8501. Press Ctrl+C in the launcher window to stop the app.

To transfer by USB, copy **AgriSense.zip** and extract it on the other PC. Each PC sets up its own environment. The ZIP includes the datasets and the app. Internet access is needed for setup, map tiles and live NASA POWER lookups. Lahore and Multan have bundled weather data for API failures.

## Read the results

The crop chart compares the eight highest-scoring crops at the selected location on a fixed 0?100 scale. Use the score to shortlist crops and see how the same crop compares across plants. The monthly charts show typical temperature and monthly rainfall over 1991?2020.

## Data and scoring

- [NASA GLDAS](https://ldas.gsfc.nasa.gov/gldas/soils) supplies the nearest 0.25-degree cell's static texture. The app masks fill values and rounds near-integer codes before lookup.
- The texture crosswalk is an approximate grouping based on [FAO field texture classes](https://www.fao.org/4/ar875e/ar875e.pdf). Codes 1-2 are light, 3-9 medium, 10-12 heavy, and 13 organic. Codes 14-16 and missing values have no crop texture group. The medium group extension includes the silt and clay loam classes. A missing texture requirement is treated as unknown, and wide is considered broad tolerance.
- [NASA POWER](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/) supplies 1991-2020 monthly T2M and PRECTOTCORR. The app multiplies monthly mm/day by days in each month and averages the 30 annual totals. It averages the monthly temperature normals within the selected season, which can cross December. Choose Rabi (November to April) or Kharif (June to October). These standard app windows apply to every crop at the selected location. They are not local planting calendars.
- [FAO ECOCROP](https://www.fao.org/geospatial/data-and-tools/data-portals/ecocrop/en) provides the optimal and absolute bounds. The app screens 2,046 rows with complete, ordered climate thresholds. A climate factor is 1 inside the optimal range, 0 beyond absolute limits, and interpolated between. Score is 100 times the product of the two climate factors. A known texture outside the stated tolerance gives zero, while preferred, tolerated, and broad matches break equal-score ties in that order.
- The score estimates compatibility from three inputs. It excludes irrigation, field-scale measurements, soil chemistry and drainage, crop calendars, extreme-temperature events, and yield.

For hosting on Streamlit Community Cloud, use this directory as the project root with app.py as the entry point.

The default field crop shortlist includes selected crops such as wheat, rice, maize, cotton, and chickpea. Zero scores are hidden from each location?s table, crop selector, and comparison bars. The growing-conditions guide shows ECOCROP preferences where available. Rainfall is an annual climate benchmark. The app has no field moisture or irrigation target. The full ECOCROP option includes other plant uses such as forage and trees.

Select **I'll irrigate** to exclude yearly rainfall from crop scores. The soil texture check still applies. Rainfall graphs remain available for context. This mode assumes you can supply enough water.

Choose **Crops** or **Trees** before running the results. Each location shows up to 25 positive scores from the selected list, or up to 50 when more than 25 matches score 100. Tree results use a year-round mean temperature and ECOCROP classifications. Frost and winter chilling are outside the tree score.

The interface supports laptop and phone screens with a single-location map, full-width mobile controls, top match cards, a searchable results table, and growing guides. For Streamlit Community Cloud, choose Python 3.12 and app.py as the entry point. GitHub hosts the source, and Streamlit hosts the running app.
