---
source: Logpaddock_SILO_API_Reference.pdf
total_pages: 40
extracted_at: 2026-04-22T07:52:23
from_cache: false
images_dir: images
---

## SILO - Australian climate data from 1889 to yesterday **Overview of SILO processes** 

SILO constructs datasets which are “ready to use” by post-processing raw observational data. Raw data records are unsuitable for most applications because observational data may: 

- Be missing values 

- Contain erroneous values 

- Not be available at or near the location of interest. 

SILO provides datasets which are: 

- Spatially complete: Gridded rasters covering Australia and some nearby islands. 

- Temporally complete: Time series datasets at point locations. Two types of point datasets are offered; datasets at: 

   1. Grid points: Daily (or monthly) time series consisting entirely of interpolated data. These records are obtained by extracting data from a selected grid cell over a time series of gridded rasters. 

   2. Station locations: Daily (or monthly) time series consisting of observed data when available, and interpolated data when observed data are missing. 

The various products are constructed as follows: 

1. Raw observational data are collated from records obtained from the Bureau of Meteorology and other providers. 

2. All available observations for a single variable and single day (or month, in the case of monthly rainfall) are assembled and spatially interpolated to create a gridded raster. This procedure is repeated for all climate variables, and all days (or months) over the period of interest (typically 1 January 1889 – present). 

3. Time series (point) datasets at station locations are constructed as follows. For each variable at a given station: 

   - a. All valid observations are assembled to create a partial time series. 

   - b. Missing values in the partial time series are “patched” with interpolated estimates. 

   - c. Any remaining missing values are patched with long term averages. This occurs when interpolated estimates are not available: 

      - i. Gridded rasters are not constructed for mean sea level pressure for years 1889-1956, nor Class A pan evaporation for years 1889-1969, as there are insufficient observational data to construct reliable surfaces. 

      - ii. Neither interpolated nor observed data are available for maximum temperature and evaporation on the previous day (SILO provides data from 1 January 1889 up to yesterday). 

      - iii. The interpolated data are flagged as being potentially erroneous. 

   - d. The dataset is augmented with source codes that indicate how each value was obtained _e.g._ observed, interpolated, long term average _etc_ . 

SILO’s data products are dynamic. While the datasets are initially created using the procedure defined above, they continually evolve: 

- _Selected_ datasets may be updated if SILO modifies the scientific methods used in their preparation. 

- _All_ datasets are periodically updated, typically every one to two years. The purpose of this update is to incorporate changes made by our data suppliers. For example, additional historic records may have become available, erroneous observations may have been identified and removed, or the coordinates of some observing stations may have been updated. 

- _Recent_ datasets are updated every night with the latest observations. Users should note that recent datasets evolve significantly due to the delay in obtaining data from some sites (while some stations report in real-time, it may be many months or even years until data are received from all stations). The nightly update typically impacts the most recent 3-12 months of each dataset. 

SILO’s gridded datasets are constructed by spatially interpolating the observational data. Ordinary kriging is used to interpolate daily and monthly rainfall, while a thin plate smoothing spline is used to interpolate minimum and maximum temperatures, Class A pan evaporation, mean sea level pressure, solar radiation and vapour pressure. An anomaly method is used to interpolate minimum and maximum temperatures, solar radiation and vapour pressure for all years up to and including 1956. Once the gridded rasters for these “primary” variables have been constructed, SILO then constructs gridded rasters for “derived” variables, such as relative humidity, vapour pressure deficit and various estimates of evapotranspiration. The derived variables are calculated on a pixel-by-pixel basis: each derived variable is calculated at each pixel using the corresponding pixel values taken from gridded rasters of the relevant input variables. 

Once all the datasets have been assembled after the nightly update, they are packed, converted and stored in formats and locations ready for clients to access: 

- The point data are stored internally in a format tailored for high speed access. When a client requests a particular dataset (using either the web interface or API), the relevant data are assembled and returned immediately. SILO also provides a mechanism that enables clients to efficiently mirror point datasets at station locations. 

- • The spatial data are converted into NetCDF and GeoTiff formats and copied to AWS Public Data . Clients can download the gridded data directly from the cloud platform, or via our web interface. 

## Climate Station Network 

SILO constructs its datasets using observational data collected at post-offices, airports, police stations, national parks, private properties etc. This network of recording _stations_ is maintained by the Bureau of Meteorology, and other organisations which contribute data to SILO. The network is constantly evolving and has varied considerably over history. The dynamic nature of the network has significant implications for the quality of SILO’s datasets. 

SILO uses interpolation techniques to construct gridded rasters and also to “patch” missing values in point datasets at station locations. The accuracy of the interpolated estimates is strongly dependent on both the number and spatial distribution of the available observations. Consequently, the quality of SILO’s gridded and patched datasets varies as the network evolves. For a quantitative estimation of the interpolation error, users should consult SILO’s primary reference . 

The number and location of stations used in the construction of SILO’s gridded datasets is shown below. 

## Variable 

RainfallMaximum TemperatureMinimum TemperatureVapour pressureAir pressureCloud oktas and/or hours of bright sunshineClass A pan evaporation 

Region Australia Queensland 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0003-03.png)


Year 

1890 (Monthly Rainfall)1900 (Monthly Rainfall)1910 (Monthly Rainfall)1920 (Monthly Rainfall)1930 (Monthly Rainfall)1940 (Monthly Rainfall)1950 (Monthly Rainfall)1960 (Monthly Rainfall)1970 (Monthly Rainfall)1980 (Monthly Rainfall)1990 (Monthly Rainfall)2000 (Monthly Rainfall)2010 (Monthly Rainfall)2020 (Monthly Rainfall)Total 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0004-00.png)


## Notes: 

- SILO’s solar radiation datasets are derived from observations of cloud oktas and/or hours of sunshine duration. 

- Statistics relate to the official station network maintained by the Bureau of Meteorology. Stations from other suppliers are not included. 

- The years 1957 and 1970 are highlighted on some plots to remind users that discontinuities may exist at those times. For further information, please see our FAQ on discontinuities. 

- Support values are used to stabilise the anomaly interpolation in data sparse regions. The support values are set to zero, so the resulting gridded dataset will be similar to the long term mean in the vicinity of each support value. For further information, please see our FAQ on the accuracy of pre-1957 datasets. 

## **Access to the Data** 

SILO products are freely available under the Creative Commons Attribution 4.0 International (CC BY 4.0)  licence. Under this licence users can copy, modify and redistribute the data, provided you acknowledge SILO as the data source and indicate if any changes were made to the data. 

The gridded datasets can be accessed using the methods outlined on our gridded data page. 

The point datasets can be accessed using either our web interface or web API: 

## Web interface 

An interactive interface that allows users to: 

- search for stations by name or number 

- view metadata about each station, including the amount of observed data 

- select stations and grid points 

- select the file format and variables required. 

After you submit your request, SILO will prepare the data and it will be returned to your browser as a file download. 

The web interface is useful for new users, and also for exploring the available point data (e.g. station number or the latitude/longitude of grid points) which can then be accessed programmatically using our web API. 

## Web API 

The API provides a programmer's interface for requesting point datasets. It can be used for streaming data back to you in real-time, for: 

- display in your browser 

- use in your own custom application 

- archiving data using command line tools such as curl  or wget . 

To construct your API requests, you can refer to the API instructions and explore the available data using the interactive web interface. 

The API is useful for automated or repetitive downloads. 

## **Data Products** 

SILO provides the following products: 

## Point datasets 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0006-00.png)


A continuous daily time series of data at either recording stations or grid points across Australia: 

Data at station locations consists of observational records which have been supplemented by interpolated estimates when observed data are missing. Datasets are available at approximately 8,000 Bureau of Meteorology recording stations around Australia. 

Data at grid points consists entirely of interpolated estimates. The data are taken from our gridded datasets and are available at any pixel on a 0.05° × 0.05° grid over the land area of Australia (including some islands). 

## Gridded datasets 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0007-04.png)


Gridded daily climate surfaces which have been derived either by splining or kriging the observational data: 

The grid spans 112°E to 154°E, 10°S to 44°S with resolution 0.05° latitude by 0.05° longitude (approximately 5 km × 5 km). 

Gridded data are provided in NetCDF and GeoTiff formats. 

The NetCDF data are arranged in annual blocks. Each annual file contains all of the daily grids for a given year and variable (or 12 monthly grids in the case of monthly rainfall). The 

GeoTiff datasets contain a single daily grid in each file (or a single monthly grid in the case of monthly rainfall). 

## **Climate Variables** 

SILO climate data are available for the following primary and derived variables on a **daily** timestep over the period **1889–present** . 

|||
|---|---|
|**Climate data**|**Variable**|
|||
||Daily rainfall|
|**Rainfall (mm)**||
||Monthly rainfall|
|||
||Maximum temperature|
|**Temperature (**℃**)**||
||Minimum temperature|
|||
||Vapour pressure|
|**V  hP**||
|**apour pressure (a)**|Vapour pressure deficit|
|||
||Class A pan evaporation|
||Synthetic estimate1|
|**Evaporation (mm)**|Combination (synthetic estimate pre-1970, class A pan 1970|
||<br>onwards)|
||Morton's shallow lake evaporation|
|**Solar radiation (MJ/m2) **|Solar exposure, consisting of both direct and diffuse components|
||Relative humidity at the time of maximum temperature|
|**Relative humidity (%)**||
||Relative humidity at the time of minimum temperature|
|||
||FAO564short crop|
||ASCE5tall crop6|
||Morton's areal actual evapotranspiration|
|**Evapotranspiration (mm)**||
||Morton's point potential evapotranspiration|
|||
||Morton's wet-environment areal potential evapotranspiration over|
||land|
|**Mean sea level pressure (hPa)**|Meansealevelpressure|
|Monthly rainfall has a monthly timestep.||



In point datasets Class A pan evaporation data are shifted to the previous day (see the FAQ "Why are evaporation data shifted to the day before?"). 

Metadata describing the primary variables and the procedures used to construct them are available in the Queensland Spatial Catalogue. 

## Variable information 

**Solar radiation** : total incoming downward shortwave radiation on a horizontal surface, derived from estimates of cloud oktas and sunshine duration[3] . 

**Relative humidity** : calculated using the vapour pressure measured at 9am, and the saturation vapour pressure computed using either the maximum or minimum temperature[6] . 

**Evaporation and evapotranspiration** : an overview of the variables provided by SILO is available here. 

## **Publications referenced** 

1. Rayner, D. (2005). _Australian synthetic daily Class A pan evaporation. Technical Report December 2005_ , Queensland Department of Natural Resources and Mines, Indooroopilly, Qld., Australia, 40 pp. 

2. Morton, F. I. (1983). _Operational estimates of areal evapotranspiration and their significance to the science and practice of hydrology_ , Journal of Hydrology, Volume 66, 1-76. 

3. Zajaczkowski, J., Wong, K., & Carter, J. (2013). _Improved historical solar radiation gridded data for Australia_ , Environmental Modelling & Software, Volume 49, 64–77. DOI: 10.1016/j.envsoft.2013.06.013. 

4. Food and Agriculture Organization of the United Nations, Irrigation and drainage paper 56: _Crop evapotranspiration - Guidelines for computing crop water requirements_ , 1998. 

5. _ASCE’s Standardized Reference Evapotranspiration Equation_ , proceedings of the National Irrigation Symposium, Phoenix, Arizona, 2000. 

6. For further details refer to Jeffrey, S.J., Carter, J.O., Moodie, K.B. and Beswick, A.R. (2001). _Using spatial interpolation to construct a comprehensive archive of Australian climate data_ , Environmental Modelling and Software, Volume 16/4, 309-330. DOI: 10.1016/S1364-8152(01)00008-1. 

For a full list of publications relevant to SILO data, please see the Publications and references page. 

## **nterpolation issues and data codes** 

SILO datasets are constructed from observational records provided by the Bureau of Meteorology . SILO interpolates the raw data, which may contain missing values, to derive datasets which are both spatially and temporally complete. 

For a brief comparison of the products available from SILO and the Bureau, please see our product comparison (PDF). 

For a detailed analysis of the interpolated surfaces provided by SILO and the Bureau, please see Beesley, C. A., Frost, A. J. and Zajaczkowski, J. (2009) A comparison of the BAWAP and SILO spatially interpolated daily rainfall datasets (PDF). 

For a full list of publications relevant to SILO data, please refer to the publications and references page. 

## Accuracy 

The accuracy of SILO’s interpolated datasets depends on both: 

- the climate variable, and 

- the number of observed values used to construct the gridded raster. 

Variables such as temperature can be reliably interpolated over significant distances because air temperature is relatively stable. In contrast, rainfall is difficult to interpolate because it is typically “patchy”. In other words the rainfall received at one location can be quite different to the rainfall received at nearby location. Regardless of the climate variable, the accuracy of a gridded dataset will, in general, be strongly dependent on the number of observations used to construct it. As the number of stations reporting data for a given variable has varied considerably throughout history, the accuracy of SILO’s gridded rasters also varies depending on the period. SILO recommends users consider both the number and location of stations used to construct gridded rasters, as it can significantly affects the accuracy of interpolated estimates. (“number and location” should be a link to the new page) 

## Data codes 

Where possible (depending on the file format), the data are supplied with codes indicating how each datum was obtained. 

|**Code**|<br>**Source**|
|---|---|
|0|Official observation as supplied bythe Bureau of Meteorology.|
|15|Deaccumulated rainfall (original observation was recorded over a period exceeding the<br>standard 24 hour observationperiod).|
|25|Interpolated from dailyobservations for that date.|
|26|Synthetic Class A pan evaporation, calculated from temperatures, radiation and vapour<br>pressure.|
|35|Interpolated from dailyobservations usingan anomalyinterpolation method.|
|42|Satellite radiation estimate from BoM|
|75|Interpolated from the longterm averages of dailyobservations for that dayofyear.|
|||



## **1. Redistribution (code 15)** 

Much of the data in Australia have been collected by volunteer observers at Post Offices, Police stations, etc. Some of these workplaces only operate on weekdays. Consequently the rainfall measured on Monday may be for the period since 9am on the preceding Friday. In such cases, SILO redistributes the accumulated rainfall back to the days when it probably fell according to the amount and days that rain fell at nearby stations. 

## **2. CLIMARC interpolation method (code 35)** 

An anomaly interpolation technique was used to construct the gridded surfaces for maximum and minimum temperatures, radiation and vapour pressure, for all years prior to 1957. The surfaces were derived, in part, using observational data made available under the CLIMARC project. Prior to the availability of the CLIMARC datasets, there were insufficient data to construct gridded surfaces so long term mean data were typically used. 

The user should note that CLIMARC interpolations: 

Are used throughout the period 1889-1956; 

Are based on relatively few observations. For example, there are data for about 60 CLIMARC stations compared to several hundred stations reporting temperature in the post-1956 period; 

Show less variation than the post-1956 data; and 

Are derived from relatively old data which in some cases contain uncorrected instrument biases. 

Consequently the interpolated CLIMARC data may not be suitable for some studies e.g. climate change detection, extreme events, number of frosts etc. 

We expect the interpolated CLIMARC data to be significantly better than long term averages. Furthermore, the CLIMARC data should preserve the daily relationships between different elements better than long term means. It should however be noted that in some areas and years, the CLIMARC data are no different to the previously supplied long term averages. For example, in Western Australia there are very few observations before 1907, and Ceduna didn't commence reporting until about 1940. Please consult the CLIMARC Report (PDF) for further information. 

## **Brief history of CLIMARC** 

CLIMARC - Computerising the Australian climate archives” (QPI43) Nick Clarkson, Queensland Centre for Climate Applications (QCCA)/DPI&F, was a joint project between the first national Climate Variability in Agriculture Program (CVAP) , the Queensland Department of Primary Industries and Fisheries (DPI&F), the Queensland Department of Natural Resources, Mines and Energy (NRM&E), and the Australian Government Bureau of Meteorology. With the aim to increase the amount of data available electronically for variables other than rainfall, for the period before 1957. When the Bureau of Meteorology commenced storing observations electronically, it decided to computerise all rainfall data but not the climate data before 1957 for cost reasons. The CLIMARC project digitised the pre-1957 climate data for 50 locations. Prior to CLIMARC there were only 5 locations in Australia where the entire observational record had been digitised. A number of other locations had already been partly digitised either by the Bureau of Meteorology or other organisations. The pre-1957 data for the 50 CLIMARC locations, together with the small amount of data which were already available, made it possible to construct gridded surfaces for the pre-1957 period. The methodology is described in the CLIMARC Report (PDF). 

## Removal of suspect values 

SILO uses a two pass interpolation system to identify and remove suspect values from the dataset used to construct a gridded surface. Suspect values are excluded from the interpolation so they do not adversely affect the gridded surface. Removal of suspect values from the interpolation also impacts SILO’s point datasets: 

Point datasets at gridded locations are constructed using the gridded surfaces. Withholding a suspect value from the interpolation will result in localised changes to the fitted surface, so point datasets in the vicinity of the withheld datum will be affected. 

Point datasets at station locations may not be consistent with interpolated data at the nearest grid point, because the station point dataset may contain observed data which were rejected by the interpolation system. 

## Grid point latitude, longitude and elevation 

Interpolated estimates are computed at the latitude and longitude at the centre of the given pixel, and if appropriate, the mean elevation for the entire pixel. 

## **Data Updates** 

Users should be aware that SILO data are constantly evolving: 

Recent datasets grow rapidly as new observational data are added (while some stations report in real-time, it may be several months until data are received from all stations); 

Older datasets may grow slowly as hand written (paper-based) records are digitised; and 

All datasets may undergo minor changes as a result of error detection programs undertaken by SILO and the Bureau of Meteorology. 

Clients requiring a static dataset for analysis should download and archive their own copy of the data. 

## Updates 

Significant updates to SILO are listed below: 

15 June 2022 

All products were updated to incorporate revised data from the Bureau of Meteorology, similar to previous updates. Users may notice: 

·         some large changes: large differences typically arise when an erroneous value has been removed from the dataset used to construct an interpolated raster. 

Data were updated over the entire period supported by SILO (1 Jan 1889 to present). 

24 September 2020 

The daily and monthly rainfall gridded surfaces were recomputed with improved scaling. The NetCDF files use scale and offset parameters to compress the data. The new values enable a wider range of rainfall values to be stored. This change only affects the NetCDF file format; the data used to compute the surfaces were not changed. 

8 July 2020 

All products were updated to incorporate revised data from the Bureau of Meteorology. The new datasets are similar to the previous datasets, however users may notice: 

·         some large changes: large differences typically arise when an erroneous value has been removed from the dataset used to construct an interpolated raster. 

·         many minor changes: small changes are expected because the long term means have been updated and the resolution has been improved in some variables (for example, the resolution of interpolated temperatures has changed from 0.5ᵒC to 0.1ᵒC). 

Data were updated over the entire period supported by SILO (1 Jan 1889 to present). 

25 September 2019 

Interpolated rainfall datasets for the period 1 January 2017 to 24 September 2019 were replaced with new datasets. The original datasets were inaccurate due to an error in the software which generates SILO’s interpolated rainfall datasets. 

April 2018 

Parameters used for normalising monthly rainfall prior to interpolation were recomputed. For further information about the normalisation procedure, please refer to the SILO reference paper. 

## Modifications 

Modifications to the observed data, station coordinates or algorithms affecting derived data are listed below: 

November 2023: 

Decline in the number of observing stations means that the previous cloud oktas/sunshine hours methodology is no longer viable and solar radiation estimates are becoming increasingly biased relative to high quality radiometers. 

Solar radiation data after 1990 is now BoM sourced satellite radiation data. Missing data has been infilled with the previous interpolated radiation data which is calculated from cloud oktas and sunshine hours. Negative satellite radiation estimates and values less than 1MJ/day set to 1MJ. 

New data code introduced to outputs (42) signifying the use of BoM satellite radiation estimate. 

This affects all previous radiation data after 1990 and those derived variables (e.g., potential evaporation) that use solar radiation in their calculation. 

## **How to Mirror SILO Datasets** 

You can maintain your own local copy of SILO datasets using the methods described below. 

If you wish to mirror SILO datasets, please read the usage information about data mirroring on our Frequently asked questions page. 

## Station datasets 

SILO provides an incremental update facility that enables clients to efficiently mirror our point datasets at _station_ locations (“patched point datasets”).  The system consists of: 

- a base dataset (updated when SILO undergoes a major update) 

- a monthly update (contains all changes since the base dataset was constructed) 

- a daily update (contains all changes since the monthly update was constructed). 

To mirror SILO's patched point datasets: 

1. Download the incremental update files from AWS Public Data  using the Amazon Web Services Command Line Interface  (CLI): 

   - a. Install  the AWS CLI 

   - b. Use the CLI sync command to mirror the data. 

For example, to mirror the files into your local target folder: aws s3 sync s3://silo-open-data/Official/PPD_mirror target --exact-timestamps 

Notes: 

- the first time you run the sync command it will download the entire dataset 

- you need to re-run the sync command every time you wish to update your local copy (sync will only download files that have changed) 

- the --exact-timestamps option is required otherwise sync will not download files which have been updated but still have the same file size. 

Note: you need to download the update files every time you wish to update your mirror. 

1. 

2. Reconstruct the patched point datasets 

   - The patched datasets can be reconstructed from the incremental updates in any way the user chooses. For example, you may wish to reconstruct datasets containing only maximum temperature for stations in Victoria and discard all other stations and variables. 

SILO provides a software package which demonstrates one method for reconstructing the patched datasets. The package contains instructions on how to install and operate the software. Please note SILO provides this software in good faith and is not responsible for its use or misuse. Download software package 

Note: SILO does not provide a facility for mirroring point datasets at grid cell locations because it would overload the system (there are approximately 290,000 grid cell locations). If you require temporal datasets at grid cell locations please download our gridded datasets and extract the relevant data. 

## Gridded datasets 

To mirror SILO's gridded datasets you can either: 

Use the Amazon Web Services Command Line Interface  (CLI): 

1. Install   the AWS CLI 

2. Use the CLI sync command to mirror the data. 

For example, to mirror the monthly rainfall rasters into your local target folder: 

aws s3 sync s3://silo-open-data/Official/annual/monthly_rain target --exact-timestamps 

## Notes: 

- the first time you run the sync command it will download the entire dataset 

- you need to re-run the sync command every time you wish to update your local copy ( sync will only download files that have changed) 

- the --exact-timestamps   option is required otherwise sync will not download files which have been updated but still have the same file size. 

## _**or**_ 

Manually download new and/or updated rasters: 

1. Download the entire set of rasters for the variable(s) that you wish to mirror. 

A list of files available for download can be obtained via URL: 

https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/index.html 

Individual files can be downloaded using the methods described on our gridded data page. For example, the monthly rainfall rasters for 1989 can be downloaded using curl   as follows: 

**curl** 'https://s3-ap-southeast-2.amazonaws.com/silo-opendata/Official/annual/monthly_rain/1989.monthly_rain.nc' 

Note: this step only needs to be done once. 

2. Each time you wish to update your local copy: 

Use the file listing: 

https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/annual/index.html 

to identify any new or updated files (see the file creation date), and then manually download the relevant file(s). 

Please note SILO data are constantly evolving so you will need to determine how often you wish to update your local copy of the data. SILO data typically change due to: 

- Nightly updates: each night SILO ingests new data which have been collected recently. This typically only impacts the most recent datasets (rainfall datasets for the preceding 12 months and other variables for the preceding 3-6 months) 

- Bulk updates: SILO periodically regenerates the entire dataset to incorporate new features or to take advantage of data improvements. This typically impacts the entire time period spanned by the affected variable(s). 

You may also wish to consider your network bandwidth and transfer costs when determining how often you update your local copy. The rasters are packed into annual files, each being around 410 MB in size for daily variables and around 14 MB for monthly rainfall. 

## **Publications and References** 

## Primary reference: 

Jeffrey, S.J., Carter, J.O., Moodie, K.B. and Beswick, A.R. (2001). _Using spatial interpolation to construct a comprehensive archive of Australian climate data_ , Environmental Modelling and Software, Vol 16/4, pp 309-330. DOI: 10.1016/S1364-8152(01)00008-1.  Available online here . 

This is the primary reference for SILO. The paper describes the algorithms used in preparing SILO datasets, including a detailed analysis of the expected accuracy of the interpolated estimates. An update (PDF) describes the reduction in errors achieved by modifications to the interpolation algorithm. 

## Metadata 

SILO metadata are available in the Queensland Spatial Catalogue. 

## Reviews 

1. Beesley, C. A., Frost, A. J. and Zajaczkowski, J. (2009). _A comparison of the BAWAP and SILO spatially interpolated daily rainfall datasets_ . 18th World IMACS / MODSIM Congress, Cairns, Australia 13-17 July 2009.  Available online here (PDF) . 

2. Tozer, C. R., Kiem, A. S., and Verdon-Kidd, D. C. (2011). _On the uncertainties associated with using gridded rainfall data as a proxy for observed_ , Hydrol. Earth Syst. Sci. Discuss., 8, 8399-8433. DOI:10.5194/hessd-8-8399-2011.  Available online here . 

## BoM Spatial Data 

1. Jones, D. A., Wang, W. and Fawcett, R. (2009). _High-quality spatial climate datasets for Australia,_ Australian Meteorological and Oceanographic Journal 58 (2009) 233-248. Available online here (PDF) . 

2. Frost, A. J., Ramchurn, A., and Smith, A. (2018). _The Australian Landscape Water Balance model (AWRA-L v6)_ . Technical Description of the Australian Water Resources Assessment Landscape model version 6. Bureau of Meteorology Technical Report. Available online here . 

## Methodology 

1. Zajaczkowski, J., Wong, K., and Carter, J. (2013). _Improved historical solar radiation gridded data for Australia_ , Environmental Modelling & Software, 49, 64–77. DOI: 10.1016/j.envsoft.2013.06.013.  Available online here . 

2. Rayner, D.P., Moodie, K.B., Beswick, A.R., Clarkson, N.M., and Hutchinson, R.L. (2004). _New Australian daily historical climate surfaces using CLIMARC_ . Queensland Department of Natural Resources, Mines and Energy Report QNRME04247.  Available online here (PDF). 

3. Carter, J.O., Flood, N.F., Danaher, T., Hugman, P., Young, R., Duncalfe, F., Barber, D., Flavel, R., Beeston, G., Mlodawski, G., Hart, D., Green, D., Richards, R., Dudgeon, G., Dance, R., Brock, D. and Petty, D. (1996). _Development of data rasters for model inputs_ , In Development of a National Drought Alert Strategic Information System Volume 3. Final Report on QPI 20 to Land and Water Resources Research and Development Corporation. 

4. Hutchinson, M.F. (1995). _Interpolating mean rainfall using thin plate smoothing splines_ , International Journal of Geographical Information Systems, 9, 385403.  Available online here . 

5. Wahba, G. and Wendelberger, J. (1980). _Some new mathematical methods for variational objective analysis using splines and cross validation_ , Monthly Weather Review, 108, 1122-1143. 

## Modelling evaporation and evapotranspiration 

An overview of the evaporation and evapotranspiration data provided by SILO is available here. 

1. Allen, R.G., Pereira, L.S., Raes, D. and Smith M. (1998). _Crop evapotranspiration - Guidelines for computing crop water requirements_ . FAO Irrigation and drainage Paper 56. Food and Agriculture Organization of the United Nations, p.300. This is the original paper for the calculation of FAO56 reference evapotranspiration. 

2. Gifford, R.M., ed (2005). Pan evaporation: An example of the detection and attribution of trends in climate variables. Proceedings of a workshop held at the Shine Dome, Australian Academy of Science, Canberra 22-23 November 2004. Available online here  . 

3. Chiew, F. H. S., and McMahon, T.A. (1991). _Applicability of Morton's and Penman's evapotranspiration estimates in rainfall-runoff modelling_ . Water Resources Bulletin, 27, 611-620. 

   - Chiew and McMahon compared Morton's wet environment evapotranspiration with Penman's potential evapotranspiration. The estimates are similar in wet conditions, but Morton's estimate is lower than Penman's in dry conditions. 

4. Doyle, P. (1990). _Modelling catchment evaporation: an objective comparison of the Penman and Morton approaches_ . Journal of Hydrology, 121, 257-276. 

5. Granger, R.J., and Gray, D.M. (1990). _Examination of Morton's CRAE model for estimating daily evaporation from field-sized areas_ . Journal of Hydrology, 120, 309325. 

This paper discusses limitations in Morton’s method: 1) The use of a water transfer coefficient that is not dependent on wind results in overestimation in low wind conditions, and underestimation in high wind conditions; and 2) The calculation of albedo may lead to significant errors. It also shows that Morton's method may not be sufficiently accurate over short accumulation periods (e.g. 24 hours). 

6. Hobbins M.T., Ramirez J.A., Brown T.C. and Claessens L.H.J.M. (2001). _The complementary relationship in estimation of regional evapotranspiration: The complementary relationship areal evapotranspiration and advection-aridity models_ . Water Resources Research, 1367-1387. 

7. Jensen, M.E., Burman, R.D. and Allen, R.G. 1990. _Evapotranspiration and Irrigation Water Requirements_ . ASCE Manuals and Reports on Engineering Practice No. 70, Am. Soc. Civil Engr., New York, NY. 332 pp. 

8. _ASCE's Standardized Reference Evapotranspiration Equation_ , proceedings of the National Irrigation Symposium, Phoenix, Arizona, 2000. Available here (PDF). 

9. Morton, F. I. (1983a). _Operational estimates of areal evapotranspiration and their significance to the science and practice of hydrology_ . Journal of Hydrology, 66, 1-76. This is the original paper for Morton's calculations including shallow lake evaporation. 

10. Morton, F. I. (1983b). _Operational estimates of lake evaporation_ . Journal of Hydrology, 66, 77-100. 

This paper provides theories of evaporation over shallow lakes, deep lakes and ponds. The algorithm used by SILO for computing Morton's shallow lake evaporation is provided in Morton, F.I. (1983a). 

11. Morton, F.I. (1986). _Practical estimates of lake evaporation_ . Journal of Climate and Applied Meteorology, 25, 371-387. 

This paper compares lake evaporation, pan evaporation and various other estimates under a range of conditions. 

12. Nash, J.E. (1989). _Potential evaporation and "the complimentary relationship"_ . Journal of Hydrology, 111, 1-7. 

This paper analyses the theoretical differences between the Morton and Penman approaches to calculating evapotranspiration. 

13. Rayner, D.P. (2005). _Australian synthetic daily Class A pan evaporation_ . Queensland Department of Natural Resources and Mines. Technical Report.  Available here (PDF). 

## Uses and Initiatives 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0019-01.png)


SILO provides data to the Queensland Government, other state and federal agencies, the CSIRO, Universities, consultants and landholders. These are some of its many uses: 

SILO provides the climate data used by: 

- CliMate , a mobile app for climate analysis. It was developed for the Managing Climate Variability Program. 

- SoilWaterApp , a mobile app for estimating soil water during fallow and early crop phases. It was developed for the Grain Research and Development Corporation. 

SILO rainfall data are used for assessing drought conditions in Queensland. 

SILO data have been used by CSIRO for evaluation of agricultural development feasibility. 

Modelling of reef catchment water quality for the annual Great Barrier Reef Report Card. 

The SILO data system began in 1996 as a collaborative project between the Queensland Government and the Australian Bureau of Meteorology to provide gap-free climate data sets for biophysical modelling, and was initially funded by the first national Climate Variability Program. 

## **Python Tools** 

This example shows how you can use Python to work with SILO’s NetCDF files. 

## Software requirements 

Python 3 is used in these examples. You will also need these Python packages: 

- numpy 

- netCDF4 

- . 

## Region mask 

The example will compute the mean annual rainfall for Queensland. To process data for a specific region, you must provide a NetCDF mask file with the same geometry as the data file(s). If you already have a mask file in another format, you may be able to convert it to NetCDF format using GDAL . 

You can download an example mask file for Queensland here (NC, 573KB) . 

## Scripts 

The script below calculates a regional mean using SILO’s monthly rainfall rasters. To compute the mean: 

1. Download all the monthly datafiles. The example uses data from 1961-1990. The data can be downloaded using a variety of methods. 

2. Create a mask file for the region of interest, or use our example mask (NC, 573KB). 

3. Run the Python script below. 

import numpy import netCDF4 

# Load the regional mask **with** netCDF4.Dataset('mask_qld.nc', 'r') **as** mask_dataset: mask_data = mask_dataset.variables['mask'][:] 

# Initialise the results list results = [] # Loop over years **for year in range** (1961, 1990): # Load the monthly rainfall data for all months in the year **with** netCDF4.Dataset('{:d}.monthly_rain.nc'.format( **year** ), 'r') **as** dataset: **data** = dataset.variables['monthly_rain'][:] # Apply regional mask to the data data.mask = mask_data.mask # Calculate the annual regional average rainfall # by computing the average across all months # and all grid points within the mask average = numpy.mean( **data** ) # Append result to the list results.append(average) 

# Output the annual average rainfall for all years print(results) 

## **NetCDF Operators (NCO)** 

This page provides an example of how to use NetCDF Operators (NCO) with SILO NetCDF files. 

## Software and data requirements 

The NetCDF Operators (NCO) toolkit is a suite of command-line programs to interact with NetCDF files. You can download pre-built binaries  or compile from source . 

## Example 1. Display the metadata 

The ncdump tool can be used to view the metadata within a NetCDF file. For example, to view the file structure and attributes of the 1981 monthly rainfall data: 

1. Download the monthly rainfall data for 1981. This can be done using a variety of methods. 

2. Run the the following command: 

**ncdump -h** 1981.monthly_rain.nc 

This shows the structure of the file ( time , lat and lon coordinates) and ancillary information such as the data packing parameters ( scale_factor , add_offset ). The truncated output of the previous example is: 

netcdf \1981.monthly_rain { dimensions: lat = 681 ; lon = 841 ; time = UNLIMITED ; // (12 currently) variables: double lat(lat) ; lat:long_name = "latitude" ; lat:standard_name = "latitude" ; lat:units = "degrees_north" ; lat:axis = "Y" ; double lon(lon) ; lon:long_name = "longitude" ; lon:standard_name = "longitude" ; lon:units = "degrees_east" ; lon:axis = "X" ; double time(time) ; time:units = "days since 1981-01-01" ; time:calendar = "standard" ; time:axis = "T" ; short monthly_rain(time, lat, lon) ; monthly_rain:_FillValue = -32767s ; monthly_rain:long_name = "Monthly rainfall" ; monthly_rain:units = "mm" ; monthly_rain:scale_factor = 0.1 ; monthly_rain:add_offset = 3250.f ; 

// global attributes: 

} 

## Example 2. Compute seasonal climatologies 

The NetCDF record averager  (ncra) can be used to compute seasonal means. 

For example, to compute the 1981-2000 summer (Dec-Jan-Feb) seasonal average: 

1. Download monthly rainfall files for 1980 to 2000. This can be done using a variety of methods. 

2. Run the record averager: 3. **ncra -F -d time** ,12,,12,3 \ 4. 1980.monthly_rain.nc 1981.monthly_rain.nc \ 5. 1982.monthly_rain.nc 1983.monthly_rain.nc \ 6. 1984.monthly_rain.nc 1985.monthly_rain.nc \ 7. 1986.monthly_rain.nc 1987.monthly_rain.nc \ 8. 1988.monthly_rain.nc 1989.monthly_rain.nc \ 9. 1990.monthly_rain.nc 1991.monthly_rain.nc \ 10. 1992.monthly_rain.nc 1993.monthly_rain.nc \ 11. 1994.monthly_rain.nc 1995.monthly_rain.nc \ 12. 1996.monthly_rain.nc 1997.monthly_rain.nc \ 13. 1998.monthly_rain.nc 1999.monthly_rain.nc \ 2000.monthly_rain.nc 1981_2000.monthly_rain.djf.nc This will write the output to file 1981_2000.monthly_rain.djf.nc . 

The arguments are as follows: 

-F invokes FORTRAN-style indexing (indices start at 1, not 0), and -d time,12,,12,3 selects data starting at time-slice 12 (December in the first file, 1981), continuing to the end (December in the last file, 2000) using a stride of 12 (looping over every year), and in each "sub-cycle" extracting 3 datasets (Dec, Jan, Feb). 

## Note on specifying input files 

On UNIX systems the list of input files can be abbreviated using regular expressions. Using the Bash shell, the list can be expressed as: 

198[123456789].monthly_rain.nc 199[0123456789].monthly_rain.nc 2000.monthly_rain.nc NCO also has an option that enables it to generate the list of input files, providing the filename contains a numeric suffix immediately before the file-type suffix. To use this option, the SILO annual files must first be renamed from <year>.<variable>.nc to <variable>.<year>.nc , so the time index (year) is immediately before the ".nc" suffix. Using this feature, the climatology example becomes: 

**ncra -F -d time** ,12,,12,3 **-n** 19,4,1 **monthly_rain** .1981.nc \ 1981_2000.monthly_rain.djf.nc where the -n option instructs ncra to load 20 files, each having a 4 -digit numeric suffix, starting with file monthly_rain.1981.nc and incrementing the numeric index by 1 to access each successive file. 

This feature is useful when computing long-term averages requiring many input files. 

## **Convert NetCDF Files** 

The examples below show how SILO’s NetCDF files can be converted to either 

- ESRI ArcASCII grids 

- GeoTiff images. 

SILO’s gridded datasets are arranged in annual blocks. The examples show how the gridded dataset for a single day can be extracted from an annual file and converted to the desired format. 

## Software requirements 

The examples use the Geospatial Data Abstraction Library  (GDAL). See the GDAL binaries  page for installation instructions, or you may wish to compile from source . 

**NOTE: It is recommended that a recent version of GDAL be used. Old versions may produce unexpected results.** 

The following examples have been tested on: 

- GDAL 2.2.1 on Windows x86-64 

- GDAL 1.9.1 on GNU/Linux x86-64. 

## Example 1. Extract a single time-slice and convert to ArcASCII format 

The following command: 

gdal_translate [annual_netcdf_file] \ [daily_arcascii_file] -of AAIGrid -ot Float32 -b [day_of_year] \ -unscale -a_nodata [missing_value] -co "DECIMAL_PRECISION=1" 

will extract a single time-slice ( day_of_year ) from the input NetCDF file ( annual_netcdf_file ), and output an ArcASCII file ( daily_arcascii_file ) in 32-bit floating point format ( Float32 ) written with one decimal place ( "DECIMAL_PRECISION=1" ). 

For example, to extract the daily grid for 1 September 1970 (244th day in the year) in ArcASCII format: 

1. Download the 1970 maximum temperature NetCDF file ( 1970.max_temp.nc ). This can be done using a variety of methods. 

2. Extract the daily grid to file 19700901.max_temp.asc : 

3. gdal_translate 1970.max_temp.nc 19700901.max_temp.asc \ 

4. -of AAIGrid -ot Float32 -b 244 -unscale -a_nodata -3276.7 \ 

   - -co "DECIMAL_PRECISION=1" 

## Example 2. Extract a single time-slice and convert to a GeoTiff image 

The following commands: 

gdal_translate [annual_netcdf_file] tmp.nc \ -of NetCDF -ot Float32 -b [day_of_year] -unscale -a_nodata [fill_value] \ -a_srs [grid_projection] gdaldem color-relief tmp.nc [colour_map_file] [daily_geotiff_file] \ -of GTiff -alpha -nearest_color_entry -co "COMPRESS=DEFLATE" 

will output the desired time-slice in GeoTiff format. The first command ( gdal_translate …) extracts the time-slice into a temporary NetCDF file ( tmp.nc ). The second command ( gdaldem …) converts the temporary NetCDF file into a GeoTiff image using the given colour map ( colour_map_file ) and compression options ( COMPRESS=DEFLATE ). 

A colour map is a text file specifying the colours used for mapping raster data to colour values. You may wish to use these sample maps which SILO constructed from images taken from the Bureau of Meteorology’s Climate Maps  website: 

- Maximum temperature (CLR, 13KB) 

- Minimum temperature (CLR, 13KB) 

- Daily rainfall (CLR, 148KB) 

- Monthly rainfall (CLR, 302KB) 

- Vapour pressure (CLR, 6KB) 

- Solar irradiance (CLR, 6KB) 

For example, to extract the daily grid for 1 September 1970 (244th day in the year) in GeoTiff format: 

1. Download the 1970 maximum temperature NetCDF file ( 1970.max_temp.nc ). This can be done using a variety of methods. 

2. Use ncdump  to read the scale and offset attributes (see the netCDF metadata) 

**ncdump -h** 1970.max_temp.nc 

3. Extract the daily grid to a temporary NetCDF file: 

4. **gdal_translate** 1970.max_temp.nc 19700901.max_temp.nc \ **-of NetCDF -a_nodata -3276** .7 **-ot Float32 -b** 244 **-unscale -a_srs epsg** :4326 

(assuming add_offset was 0.0 and scale_factor was 0.1). 

5. Convert the temporary file to GeoTiff: 

6. gdaldem color-relief 19700901.max_temp.nc max_temp.clr \ 

7. 19700901.max_temp.tif -of GTiff -alpha -nearest_color_entry \ -co "COMPRESS=DEFLATE" 

## **API Tutorial** 

SILO provides an Application Programming Interface (API) that enables you to obtain point datasets by encoding your request in a URL. Once you have constructed the URL, the data can be downloaded: 

- via a web browser 

- using command line tools such as curl  or wget 

- directly to your application (for example, using the urllib  package in Python). 

This tutorial will get you up and running quickly with the API. Code snippets are in Python, however the same principles apply for other programming languages. Let's begin by testing the API in your browser. To get a list of stations with "Cairns" in the station name, type the following into your browser's address bar: 

https://www.longpaddock.qld.gov.au/cgibin/silo/PatchedPointDataset.php?format=name&nameFrag=cairns The response should look similar to this (formatted here for readability): 

31010|CAIRNS POST OFFICE                       | -16.933| 145.783|QLD |    2.0| 31011|CAIRNS AERO                              | -16.874| 145.746|QLD |    2.2| 

If the lines are not displayed properly, you may need to right-click your mouse and select "View page source" (Chrome, Firefox) or "View source" (Internet Explorer), or press F12 (Microsoft Edge). 

The API provides tools for searching for stations. Once you have selected a station, you can get point data for the station by typing the data request into your browser's address bar. For example, to obtain data in “alldata” format for Cairns Post Office (station 31010) between 1 January 2011 and 10 January 2011: 

https://www.longpaddock.qld.gov.au/cgibin/silo/PatchedPointDataset.php?start=20110101&finish=20110110&station=31010&format=alld ata&username=<email_address> 

You will need to replace <email_address> with your email address. You should see a response which looks similar to this (formatted here for readability): 

Date       Day Date2      T.Max Smx T.Min Smn Rain   Srn  Evap Sev Radn   Ssl VP    Svp RHmaxT RHminT  FAO56  Mlake  Mpot   Mact   Mwet  Span   Ssp   EvSp Ses MSLPres Sp (yyyymmdd)  () (ddmmyyyy)  (oC)  ()  (oC)  ()   (mm)  ()  (mm)  () (MJ/m2) () (hPa)  ()   (%)    (%) (mm)   (mm)   (mm)   (mm)   (mm)   (mm)  ()   (mm)  () (hPa)   () 20110101     1  1-01-2011  28.5  25  25.0  25   26.7  25   3.8  25   7.0   25  31.0  25   79.7   97.9    2.0 2.1    2.3    1.8    2.1    2.8  26    3.8  25 1008.5  25 20110102     2  2-01-2011  28.0  25  23.5  25   80.2  25   1.6  25   7.0   25  30.0  25   79.4  100.0    1.9 2.1    2.1    2.0    2.0    2.8  26    1.6  25 1009.0  25 20110103     3  3-01-2011  30.5  25  24.0  25    5.0  25   4.0  25  16.0   25  30.0  25   68.7  100.0    3.8 4.9    5.1    4.5    4.8    4.9  26    4.0  25 1009.5  25 20110104     4  4-01-2011  31.0  25  23.0  25   29.2  25   5.0  25  22.0   25  28.0  25   62.3   99.7    4.9 6.5    6.7    5.9    6.3    6.2  26    5.0  25 1007.5  25 20110105     5  5-01-2011  32.0  25  23.5  25    3.1  25   7.0  25  25.0   25  29.0  25   61.0  100.0    5.5 7.4    7.5    6.8    7.2    6.9  26    7.0  25 1006.5  25 20110106     6  6-01-2011  32.0  25  24.5  25    0.0  25   3.2  25  20.0   25  29.0  25   61.0   94.4    4.8 6.2    6.8    5.3    6.1    6.1  26    3.2  25 1005.5  25 20110107     7  7-01-2011  32.5  25  24.0  25    7.6  25   6.2  25  25.0   25  29.0  25   59.3   97.2    5.6 7.4    7.8    6.7    7.2    7.0  26    6.2  25 1003.5  25 20110108     8  8-01-2011  32.0  25  24.5  25    0.5  25   5.2  25  24.0   25  30.0  25   63.1   97.6    5.4 7.2    7.4    6.7    7.0    6.6  26    5.2  25 1004.5  25 20110109     9  9-01-2011  33.0  25  25.0  25    0.0  25   5.8  25  21.0   25  31.0  25   61.6   97.9    5.0 6.6    7.0    5.9    6.5    6.3  26    5.8  25 1002.5  25 20110110    10 10-01-2011  31.5  25  24.0  25   15.4  25   5.6  25  25.0   25  28.0  25   60.6   93.9    5.5 7.3    7.7    6.5    7.1    6.9  26    5.6  25 1001.5  25 

If not, read the error message and ensure you have structured the request properly. 

As another example, to obtain data in “alldata” format for the grid point location 23 degrees South, 135 degrees East, between 1 January 2011 and 10 January 2011: 

https://www.longpaddock.qld.gov.au/cgibin/silo/DataDrillDataset.php?start=20110101&finish=20110110&lat=23.00&lon=135.00&format=alldata&username=<email_address>&password=apirequest You should see a response which looks similar to this (formatted here for readability): 

Date       Day Date2      T.Max Smx T.Min Smn Rain   Srn  Evap Sev Radn   Ssl VP    Svp RHmaxT RHminT  FAO56  Mlake  Mpot   Mact   Mwet  Span   Ssp   EvSp Ses MSLPres Sp (yyyymmdd)  () (ddmmyyyy)  (oC)  ()  (oC)  ()   (mm)  ()  (mm)  () (MJ/m2) () (hPa)  ()   (%)    (%) (mm)   (mm)   (mm)   (mm)   (mm)   (mm)  ()   (mm)  () (hPa)   () 20110101     1  1-01-2011  32.0  25  23.0  25    4.5  25   4.2  25  17.0   25  27.0  25   56.8   96.1    4.4 5.4    6.3    4.3    5.3    6.8  26    4.2  25 1008.5  25 20110102     2  2-01-2011  37.0  25  22.0  25    1.3  25   8.4  25  28.0   25  24.0  25   38.2   90.8    7.2 8.2    9.5    4.8    7.1   10.9  26    8.4  25 1009.0  25 20110103     3  3-01-2011  38.5  25  20.0  25    0.0  25   9.8  25  30.0   25  16.0  25   23.5   68.5    8.1 8.3   11.7    2.5    7.1   12.7  26    9.8  25 1008.0  25 20110104     4  4-01-2011  39.0  25  22.0  25    0.0  25  11.4  25  25.0   25  17.0  25   24.3   64.3    7.5 7.2   11.3    1.3    6.3   11.8  26   11.4  25 1005.5  25 20110105     5  5-01-2011  35.5  25  22.5  25    0.1  25   9.8  25  23.0   25  17.0  25   29.4   62.4    6.7 6.6   10.1    1.3    5.7   10.3  26    9.8  25 1006.5  25 20110106     6  6-01-2011  38.0  25  23.0  25    0.0  25  10.6  25  28.0   25  20.0  25   30.2   71.2    7.6 8.1   11.0    3.0    7.0   11.8  26   10.6  25 1006.0  25 20110107     7  7-01-2011  37.0  25  23.5  25   13.5  25   8.8  25  26.0   25  19.0  25   30.3   65.6    7.3 7.5   10.8    2.3    6.5   11.2  26    8.8  25 1002.0  25 20110108     8  8-01-2011  36.5  25  23.0  25    5.3  25  10.2  25  22.0   25  25.0  25   40.9   89.0    6.1 6.8    8.5    3.6    6.1    9.4  26   10.2  25 1002.5  25 20110109     9  9-01-2011  33.0  25  22.0  25   26.3  25   6.4  25  22.0   25  26.0  25   51.7   98.4    5.4 6.5    7.4    5.2    6.3    8.2  26    6.4  25 1004.0  25 20110110    10 10-01-2011  35.0  25  23.0  25    0.0  25   9.8  25  24.0   25  20.0  25   35.6   71.2    6.6 6.9    9.5    2.5    6.0   10.0  26    9.8  25 1001.5  25 

Most datasets can be requested using a single API call. The RAINMAN format however, consists of 6 datafiles and a Readme file containing metadata. The 7 files can be downloaded using an API call for each file: 

https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?format=rainman&comment=rain&start=20110101&finish=2011 0110&station=31010&username=<email_address> https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?format=rainman&comment=tmax&start=20110101&finish=201 10110&station=31010&username=<email_address> https://www.longpaddock.qld.gov.au/cgibin/silo/PatchedPointDataset.php?format=rainman&comment=tmin&start=20110101&finish=2011 0110&station=31010&username=<email_address> https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?format=rainman&comment=evap&start=20110101&finish=201 10110&station=31010&username=<email_address> https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?format=rainman&comment=vp&start=20110101&finish=20110 110&station=31010&username=<email_address> https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?format=rainman&comment=rad&start=20110101&finish=20110 110&station=31010&username=<email_address> https://data.longpaddock.qld.gov.au/static/silo/resources/Readme.txt 

You can also customise your request instead of using one of our predefined formats. For example, to obtain data for maximum and minimum temperatures for Cairns Post Office (Station 31010) between 1 January 2011 and 10 January 2011: 

https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?start=20110101&finish=20110110&station=31010&format=jso n&comment=XN&username=<email_address> 

You should see a response which looks similar to this (formatted here for readability): 

{ "station": { "name": "CAIRNS POST OFFICE", "number": 31010, "latitude":  -16.9333, "longitude": 145.7833, "elevation":   2.0, "reference": "" }, "extracted":20190626, "data": [ { "date": "2016-01-01", "variables": [ { "source": 25, "value":    28.5, "variable_code": "max_temp" }, { "source": 25, "value":    23.0, "variable_code": "min_temp" } ], { "date": "2016-01-02", "variables": [ { "source": 25, "value":    30.5, "variable_code": "max_temp" }, { "source": 25, "value":    23.0, "variable_code": "min_temp" } ] } ] } In the example above, the "comment=XN" field in the API request was used to request maximum and minimum temperatures. The codes for requesting other variables are provided in the API reference. 

Now that we know the API is working, let's write a Python program to query it. We're going to use Python 3 to download print a small dataset. 

**import** urllib.request **import** urllib.parse 

api_url = 'https://www.longpaddock.qld.gov.au/cgi-bin/silo' 

params = { 'format': 'standard', 'lat': '-30.00', 'lon': '135.00', 'start': '20160101', 'finish': '20160105', 'username': <email_address>, 'password': 'apirequest' } url = api_url + '/DataDrillDataset.php?' + urllib.parse.urlencode(params) 

**with** urllib.request.urlopen(url) **as** remote: data = remote.read() 

print(data) You can also obtain data using command line tools such as curl  or wget . 

#!/bin/bash 

api_url="https://www.longpaddock.qld.gov.au/cgi-bin/silo" begin="20160101" end="20160105" username=<email_address> password="apirequest" 

# Request "APSIM" data at a grid location lat="-30.00" lon="135.00" wget -O my_data -o my_log "$api_url/DataDrillDataset.php?lat=$lat&lon=$lon&start=$begin&finish=$end&format=apsim&username =$username&password=$password" 

# **Note:** the data will be stored in the "my_data" file, and the wget logging information stored in the "my_log" file. 

# Request vapour pressure data in CSV format at a station location station="1018" curl "$api_url/PatchedPointDataset?station=$station&start=$begin&finish=$end&format=csv&comment=V& username=$username" That's it! We recommend you also read the guide, which contains important information about the SILO Web API. For more details on the available resources, please consult the reference. 

## **API Guide** 

The SILO Web Application Programming Interface (API) allows you to query point datasets, as well as a range of metadata, in real time. 

## Accessing the API 

The SILO API has the following base URL: 

https://www.longpaddock.qld.gov.au/cgi-bin/silo For example, a request for point data might look like: 

https://www.longpaddock.qld.gov.au/cgibin/silo/PatchedPointDataset.php?station=1018&start=20170101&finish=20170228&format=alldata&u sername=<email_address> For detailed information about request parameters please consult the reference. 

## Available data 

The following data are available through the SILO API: 

- Point data (an API request provides data for a single station location or grid cell location) 

The following metadata are available: 

- Stations 

## Identification 

Data requests must be accompanied by your email address. We need your email address in case we need to contact you about the service. 

## Output formats 

Point data are available in CSV and JSON, as well as a number of predefined formats, all of which are returned as plain ASCII text. 

Metadata are provided in plain ASCII text. 

You can specify your desired format using the format query parameter. For example: 

https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php?format=json 

## Requests 

API requests are standard HTTP calls. The SILO API allows for retrieval of data only, so the API only supports HTTP GET methods. It's possible to use the API simply by typing the URL into your browser. The API can also be queried by a program. Here is a simple example in Python: 

**import** urllib.request 

r = urllib.request.urlopen('https://www.longpaddock.qld.gov.au/cgibin/silo/PatchedPointDataset.php?format=name&nameFrag=Cairns') data = r.read() print(data) 

The API can also be queried by command line tools. Here is a simple example using wget : 

wget -O Cairns_stations 'https://www.longpaddock.qld.gov.au/cgibin/silo/PatchedPointDataset.php?format=name&nameFrag=Cairns' # **NOTE:** you may need to set proxy environment variables to pass through your local firewall 

## Responses 

Data are returned in the format requested. However users should note the following: 

- fields in JSON objects are unordered and may be returned in any order 

- fields in CSV files are ordered by variable, with commonly used variables (such as rainfall and temperature) appearing first. 

## **API Reference** 

## Patched Point data 

API request returns a single point dataset at a station location. 

## **Attributes** 

The attributes for a point data request vary depending on the format and data type requested. 

## **Routes** 

**Get point data** 

|**HTTP method**|<br>GET|<br>GET||||||
|---|---|---|---|---|---|---|---|
|**URI**|/PatchedPointDataset.php|||||||
|**Parameters**||**Name**<br>start|**Required**<br>yes|**Default**|<br>**Type **<br>string|<br>**Description**<br>The first date toget data for,formatted asYYYYMM||



||finish|yes||string|string|string|
|---|---|---|---|---|---|---|
||station|yes||int|||
||||||||
||||||||
||||||•||
|||||||<br>parameter):|
|||||||**Format name**|
|||||||JSON|
|||||||CSV(Comma-Separated Values)|
||||||•|Predefined formats:|
|||||||**Format name**|
|||||||Standard|
||format|yes||string|||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||||
||||||•||
||username|<br>yes||string|||
||||||||
|||yes if CSV, JSON,|||||
|||<br>or RAINMAN|||||
||comment|<br>format is specified||string|||
||||||||
|||no otherwise|||||
||||||||



NOTE: you will need to replace <email_address> with your email address in all the example requests below. 

https://www.longpaddock.qld.gov.au/cgi- 

The response for a point data request will vary depending on the format requested. Please see the file formats and samples page for a sample of each format. 

## **Frequently Asked Questions** 

## **How many stations are used to construct the gridded rasters?** 

The number of stations recording data has varied considerably throughout history. Our summary information shows the evolution of the station network over time, as well as the spatial distribution of stations on selected dates. Users wishing to conduct a detailed analysis should download the interpolation log files. These files can also be used to determine which stations were used to construct the gridded raster for a specific variable and date. 

## **How can I get a list of the patched stations?** 

You can use the API to search for stations within a given radius of a known station. To obtain a list of the patched stations you could search for stations within a 10,000km radius of Alice Springs Post Office (station 15540): 

https://www.longpaddock.qld.gov.au/cgi- 

bin/silo/PatchedPointDataset.php?format=near&station=15540&radius=10000 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0031-09.png)


## **Are there download limits?** 

Yes, SILO monitors both the number of data requests being made and also the volume of data being downloaded. We do this to ensure: 

1. the system is being used fairly ( _i.e._ excessive requests by one user are not preventing other users from obtaining data) 

2. we can continue to provide the service free of charge. 

If you find your data requests are being blocked, you may be able to mirror the datasets you are interested in. If mirroring is not a suitable solution, please contact us so we can discuss your needs. 

## **Why are some stations missing?** 

SILO provides point datasets at approximately 8000 station locations and approximately 280,000 grid cell locations (i.e. all cells which are over land). 

When selecting stations on our web interface, you may find that some stations appear to be missing. While data are available for all 8000 stations, only those stations which meet the specified "data quality" criteria are shown. You can adjust these criteria using the buttons and slider bars below the map. For example: 

1. to show all stations with rainfall data, regardless of how much observed data each station has, you should select the option for including "Rainfall", deselect the options for including "Temperature" and "Class A pan evaporation", and set the "Percent observed" to zero. 

2. to show all stations which have 90% observed data for Rainfall and Temperature in the 1980s and 1990s, you should select the options for including "Rainfall" and "Temperature", deselect the option for including "Class A pan evaporation", set the "Percent observed" to 90% and set the "Decades of interest" to 1980-2000. This will limit the stations to those having observed data for rainfall, minimum temperature and maximum temperature, for 90% of the days between 1 Jan 1980 and 31 Dec 1999 (inclusive). 

## **Why are there differences between point data at grid cells and the corresponding gridded surfaces?** 

The time-series data at a given grid cell should be the same as the data extracted from a time-series of gridded surfaces at the same location. Differences can arise when the gridded values are considered suspect and replaced by long term daily mean values. 

When a point dataset is requested at a grid cell location, the data are: 

1. extracted from the relevant grid cell in the gridded datasets 

2. passed through a simple filter that checks if each datum is within an acceptable range: 

   - daily rainfall: 0 – 1300 mm 

   - maximum temperature: -9 - 54 ᵒC 

   - minimum temperature: -20 - 40 ᵒC 

   - class A pan evaporation: 0 - 35 mm 

   - solar radiation: 0 - 35 MJ/m2 

   - vapour pressure: 0 - 43.2 hPa 

   - maximum temperature > minimum temperature 

If a given datum (or pair of data values for the Tmax > Tmin check) fails the check, it (or they) may be erroneous. In this situation SILO provides the long term daily mean(s) instead of the suspect value(s). A source code is provided in many of the file formats provided by SILO; the source code indicates the source of each datum and thereby enables users to identify when the aforementioned substitutions have occurred. 

The same checks are done when a point dataset is requested at a station location; the main difference is observed data are provided where possible, and gridded data are provided if observed data are not available on a given day(s). 

## **Do you provide customised datasets?** 

No. All SILO data products are now available through our self-service website in a range of formats. 

**Do I need an account?** 

No, you do not need an account to access SILO data. 

## **Why do I need to provide my email address?** 

You must provide a valid email address when requesting point datasets via our website or API. 

SILO requires your email address so we can contact you: (i) if there are problems with the way SILO is being accessed; or (ii) to provide critical information such as updates to datasets or system failures. 

We will only use your information for this purpose. It will otherwise not be used or disclosed unless authorised or required by law. Your personal information will be handled in accordance with the Information Privacy Act 2009. For further information, please see our Privacy Statement. 

## **What are the differences between point data and gridded data?** 

Point datasets are temporal datasets at a single location. In other words, they provide a timeseries of data (usually daily time-step) at either a single grid cell or a single station. 

Gridded datasets are spatial datasets for a given date. SILO grids cover the region 112°E to 154°E, 10°S to 44°S with resolution 0.05° longitude by 0.05° latitude (approximately 5 km × 5 km). 

**What is the difference between point data at grid points and station locations?** Station point datasets are a time series of data at a station location, consisting of station records which have been supplemented by interpolated estimates when observed data are missing. Station point datasets are available at approximately 8,000 station locations around Australia. These datasets were formerly known as SILO Patched Point datasets. 

Grid point datasets are a time series of data at a grid point location consisting entirely of interpolated estimates. The data are taken from our gridded datasets and are available at any grid point over the land area of Australia (including some islands). The nominal grid location (where the interpolated surface is evaluated) is the _centre_ of the corresponding grid cell. These datasets were formerly known as SILO Data Drill datasets. 

## **What happened to Patched Point and Data Drill datasets?** 

Both datasets are still available, but as they can now be requested through the same interface, the distinction between them is no longer required. For further information, see the previous question. 

## **Why does the "comparison" predefined format change?** 

The comparison format is intended for people to use to decide what data they need, so when new variables are added to Silo they are included in the comparison format. 

**Are point data interpolated or observed?** 

Point datasets at grid locations consist entirely of interpolated data. Point datasets at station locations contain observed data (when available) and interpolated data (when observed data are not available or do not pass Quality Assurance tests). 

**What tools can I use to view, convert or process NetCDF rasters?** There are many open source and commercial tools  available for working with NetCDF rasters. You might find the following tools helpful: 

- Viewing: Ferret , Panoply and GIS tools such as QGIS . 

- Command line manipulation: NCO and CDO . 

- Programming APIs: Python NetCDF4 and native NetCDF libraries for C, C++ and FORTRAN. 

NetCDF files can be converted to a wide range of GIS formats using GDAL . 

**What time are observations made?** 

For most daily climate variables the observations are recorded at 9 am. To assist in understanding how SILO datasets are constructed, it may be useful to see how data are assigned to a given day: 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0034-09.png)


**Why are evaporation data shifted to the day before?** 

Evaporation (class A pan) is measured at 9am. In normal circumstances a large proportion of the observed evaporation would have occurred throughout the daylight hours (after 9am) on the previous day. Consequently, SILO shifts evaporation data to the day before the observation was made. Please note the adjustment is only applied to SILO’s point datasets; the day shift is not applied to SILO’s gridded evaporation datasets. 

Note: the Bureau of Meteorology shifts maximum temperature data to the previous day for similar reasons. SILO uses the shifted temperature data provided by the Bureau. 

## **How are gridded rainfall datasets created?** 

Daily rainfall gridded datasets are derived from interpolated monthly rainfall by partitioning the monthly total onto individual days. Partitioning requires estimation of the daily distribution throughout the month. The distribution is obtained by direct interpolation of daily rainfall data throughout the month. At the end of the month, the interpolated monthly rainfall is then partitioned onto individual days according to the computed distribution. 

For further information, please read the journal article  which documents many of SILO's processes, and also our metadata. 

**Can I request point data for a large number of locations through the website?** No, data can only be requested for one location when using the website to order data. If you wish to request data for a large number of locations, you may wish to consider using our API. 

**How can I repeat a data request for the same set of stations (or grid points)?** 

If you wish to repeat a previous request or automate requests, we suggest you try our API rather than manually entering requests via the interactive web page. 

## **SILO has data for 29-Feb-2000 but not for 29-Feb-1900, is this right?** 

Yes. Under the Gregorian calendar 2000 was a leap year, but 1900 wasn't. Normally if the year can be evenly divided by 100 it is not a leap year, however it is a leap year if it can be evenly divided by 400. 

**How are the grid locations selected?** 

The nominal location for a given grid cell is the _centre_ of the cell. For example, the value at 115.05° East, 34.00° South is intended to be representative of the area 115.025° - 115.075° East, 33.975° - 34.025° South. 

You can request data for any grid cell that is not masked out. Grid cells over the ocean and some islands are masked out. If you request data at a location where the longitude or latitude is not a multiple of 0.05°, the location will be rounded to the nearest 0.05°. If you request data at a location that lies exactly on the edge of a grid cell, the longitude (or latitude) will be rounded up giving you data from the grid cell that is east of the cell edge (if the specified longitude lies on a cell edge), or north of the cell edge (if the specified latitude lies on a cell edge). 

## **Can you provide interpolated data at resolutions higher than 0.05° × 0.05°?** 

No. The accuracy of the interpolated datasets is strongly dependent on the density of the input data (i.e. station density). In most regions the station density is not high enough to support higher resolution estimates. 

Users should also note that the interpolated estimates are based on observations recorded in a standard Stephenson screen or equivalent, placed in an open and usually flat area. It does not represent the ground level climate of some areas (e.g. wooded systems) and does not address all the issues associated with slope and aspect. Users may need to implement their own microclimate adjustments. 

## **How accurate are the interpolated data prior to 1957?** 

The number of stations recording climate variables significantly increased around 1957 – the International Geophysical Year. An anomaly interpolation technique is used to interpolate maximum and minimum temperature, radiation and vapour pressure for all years prior to 1957. The anomaly method is better able to interpolate sparse datasets than direct interpolation because much of the variance can be captured by the long term mean. The anomaly method works as follows: (i) the _anomaly_ at each station is computed by subtracting the long term daily mean (for the given station and variable) from each observed value; (ii) the anomaly data are interpolated using a smoothing spline; (iii) at each pixel the interpolated long term daily mean (for the given variable) is added to the interpolated anomaly. To further improve the interpolation, SILO uses "support" values to support the spline in data sparse regions. The support values are set to zero _(i.e._ the anomalies are zero at all support locations), so the resulting gridded dataset will be similar to the long term mean in the vicinity of each support value. 

The data quality throughout the pre-1957 period was examined in: Rayner, D.P., Moodie, K.B., Beswick, A.R., Clarkson, N.M., and Hutchinson, R.L. (2004), _New Australian daily historical climate surfaces using CLIMARC_ . Queensland Department of Natural Resources, Mines and Energy Report QNRME04247. Available here. 

## **Are SILO data quality checked?** 

SILO datasets are constructed from observational data collected by the Bureau of Meteorology. The Bureau has a quality assurance program which is progressively checking its observational collection. SILO does not use data which have been quality checked by the Bureau and classified as "wrong", "suspect" or "inconsistent with other known information". In addition, SILO implements a number of internal checks to identify data which may be erroneous. For example, SILO uses a "two-pass" interpolation technique  to interpolate all variables except daily rainfall. Observed data are interpolated in a first pass and residuals computed for all data points. The residual is the difference between the observed and interpolated values. Data points with high residuals may be indicative of erroneous data and are excluded from a subsequent interpolation which generates the final surface from which the station-point datasets are constructed. 

**Is it possible that minimum temperatures are higher than maximum temperature?** No. Maximum temperature observations are shifted to the previous day (see above), so the observed maximum should always be lower than (or equal to) the minimum temperature. 

**Why are the observed data and interpolated data different?** 

The observed data for a given station should be _similar_ to the corresponding interpolated data at the nearest grid cell. However differences can arise for several reasons: 

1. interpolated data are evaluated at the centre of the grid cell. If the station is a significant distance from the cell centre, and the interpolated surface exhibits a strong gradient in the area, there can be a significant difference between the value at the station and the cell centre. For example, under normal conditions the temperature usually decreases with elevation at approximately 5-7 °C/km. If the elevation at the cell centre is 500m higher than the station (quite possible in alpine regions), the temperature at the cell centre could be 2.5-3.0 °C lower than the temperature at the station. 

2. most of SILO's interpolated grids are constructed using a smoothing spline. If the input data are spatially homogeneous, the fitted surface will generally pass through ( _i.e._ reproduce) the input data. However if the input data are highly variable or contain errors, the spline may smooth the data and consequently the fitted surface will not reproduce the input data in the affected area(s). Note: SILO uses kriging to interpolate daily and monthly rainfall. Kriging guarantees the input data are reproduced. 

3. SILO uses a "two-pass" interpolation technique to interpolate all variables except daily rainfall. Data rejected in the first pass are excluded from the dataset used to construct the interpolated grid in the second pass. Consequently, if a given datum has been rejected by SILO's interpolation system, the fitted surface may differ substantially from the observed datum at that location. Users should note that data rejected by the interpolation system are included in the point (station) datasets and can be identified by their source flag. Users wishing to exclude such observations can replace them with interpolated estimates by requesting the corresponding data at the nearest grid cell. 

## **Are the data suitable for determining the rates of changes in temperature, rainfall, evaporation, etc., caused by climate change?** 

SILO data are not intended for use in climate change detection studies. Small data movements caused by climate change can be easily be confounded by changes resulting from instrumental biases and relocating recording stations. For climate change detection we recommend using the Bureau's ACORN-SAT  and High-Quality  datasets. 

## **Can I mirror SILO's datasets?** 

The gridded datasets are stored on Amazon Web Services' Public Data  repository in an S3 bucket . The files can be mirrored using the AWS command line utilities for working with S3 datasets . For example, the monthly rainfall rasters can be mirrored to your current directory using the _sync_ command: 

aws s3 sync s3://silo-open-data/annual/monthly_rain/ . 

SILO’s point datasets at _station_ locations can be mirrored using the procedure described on our mirroring page. If this approach is not suitable for your application, you may be able to use our API (it is designed for repetitive or automated tasks). 

SILO’s point datasets at _grid cell_ locations cannot be easily mirrored because: 

- there would be a large number of files, approximately 290,000 (one for each grid cell over land). 

- every raster file ( _i.e._ NetCDF or GeoTiff file containing gridded data) can change every day, although changes usually only occur in grids for the most recent 12 months. (Data can change for a variety of reasons; see the next question below). 

If you need to mirror point datasets at _grid cell_ locations, you should consider building your own point datasets from our gridded datasets. The desired point datasets can be built by extracting the relevant pixel values from a time-series of gridded datasets. The gridded data can be efficiently downloaded because they are arranged in annual blocks, with each annual file containing all of the grids for the selected year and variable. Please note this approach is not possible if you are seeking point datasets at _station_ locations. 

If you need to mirror any SILO dataset, please consider: 

- mirroring data for only those locations and variables that you really need. 

- an incremental approach. For example, you could _occasionally_ download data for the entire time period required (e.g. every six months to capture major changes to the data), and _frequently_ update only the most recent 3 months of each dataset (e.g. every week to capture nightly changes to the data). 

Please remember SILO data are provided free of charge under the Queensland Government's Open Data program. In addition to the operational cost of maintaining the system, SILO also pays data egress charges for the data downloaded by our clients. We therefore ask you to carefully consider your data requirements before downloading large volumes of point data. 

## **Why do SILO data change?** 

SILO data are constantly evolving. The changes can be a result of changes in the raw data or changes in SILO methodology. Recent datasets grow rapidly as new observational data are added (while some stations report in real-time, it may be many months or even years until data are received from all stations). The data are also subject to corrections and updates by the Bureau, so there can be ongoing changes to the raw data used to construct SILO datasets. 

SILO actively seeks techniques for improving data quality and may implement changes which modify our interpolated estimates or derived variables. Users requiring static datasets (e.g. for model calibration) should archive their own copy of the data, as they should not rely on SILO supplying exactly the same dataset at different points in time. 

## **When does the nightly update occur?** 

SILO is updated every night with new data from the Bureau of Meteorology. The update commences at 9:30 pm (AEST) and is usually completed by midnight. 

## **Do you have any metadata describing SILO datasets?** 

Yes. Metadata are included in the NetCDF and GeoTiff gridded datasets, and formal metadata are provided on our metadata page. 

## **How can I import SILO point datasets into Microsoft Excel?** 

The data must be in a format that Excel can recognise. When requesting point data in: 

- a customised format, you should select the CSV (comma-separated values) option. Excel will be able to read the .csv file directly. 

- one of the fixed ( _i.e._ predefined) formats, the data are delivered as plain ASCII text. To import the data into Excel: 

   1. In the ‘File Menu’, select 'Open' 

   2. In the pop-up window, change the file filter (in the bottom-right corner) from ‘All Excel Files’ to ‘All Files’ 

   3. Select the SILO data file and click on ‘Open’ 

   4. In the ‘Text Import Wizard’ pop-up window, select ‘Delimited’ and click on ‘Next’ 

   5. Select 'Space' in the list of delimiters and click on ‘Next’ 

   6. Click ‘Finish’ to load the dataset. 

Please note you may need to slightly modify these procedures depending on your version of Excel. 

**How can I select grid points when they are not shown on the map?** 

The regular array of grid points is only shown when the map resolution is high enough to display them. You can either: (i) zoom in to the region of interest until the grid points automatically appear. They will appear when the scale is 3km or less (the scale is shown in the bottom left corner of the map); or (ii) enter the latitude and longitude of the location you require in the search box. The map will automatically shift focus to that location and show the grid points. 

**How does the quality of the Class A pan evaporation rasters vary?** The number of stations reporting Class A pan observations has declined in recent years: 


![](docs/_tmp_images/Logpaddock_SILO_API_Reference.pdf-0039-11.png)


The accuracy of an interpolated raster is strongly influenced by the number of observations that were used to construct it. Consequently we expect SILO’s Class A pan evaporation rasters to be declining in accuracy and therefore recommend clients consider using alternatives, such as our synthetic estimate. For further information, please read our evapotranspiration documentation. 

## **Should I use the most recent Class A pan evaporation rasters?** 

Class A pan evaporation observations are available from some stations in near real-time, while it may take a few months before the data from other stations are available. This has consequences for the accuracy of the most recent rasters, because the quality of an interpolated raster depends on the number of observations used to construct it. The delay between when a Class A pan measurement was recorded and when it becomes available for inclusion in SILO’s rasters is shown in the Table below. 

|**Days/months after observation date**|**Number of reports***|
|---|---|
|2 days|50-55|
|0 to 2 months|55-60|
|3 months|80-85|
|4 months|95-115|



Please note the Bureau’s network of recording stations and data processing methods are continually evolving. The data in the above table reflect the situation in late 2019 

Given the limited number of stations used to construct the most recent Class A pan evaporation rasters, we recommend clients consider using the alternatives outlined in our evapotranspiration documentation. 

## **Why are there discontinuities and trends in some datasets?** 

Trends can arise for a range of reasons, but the two most common reasons are: 

- climate change 

- systematic drift in instruments used to record data. 

Discontinuities can arise for many reasons, such as: 

- a change in the type of device used to record a given climate variable 

- a recording station may have been relocated a short distance 

- the environment around a given station may have changed (e.g. tree growth) 

- the methods used by SILO may change (users should note that different algorithms are used for constructing datasets in the years before 1970 (evaporation) and 1957 (most of our “core” variables). For further information, please see our overview of SILO processes, and SILO’s primary reference. 


---

## Extracted Images

| # | File | Page | Dimensions | Size |
|---|------|------|------------|------|
| 1 | figure_1.png | 3 | 900x500 | 29.8KB |
| 2 | figure_2.png | 4 | 900x750 | 89.8KB |
| 3 | figure_3.png | 6 | 2917x2292 | 119.5KB |
| 4 | figure_4.jpeg | 7 | 600x472 | 30.5KB |
| 5 | figure_5.jpeg | 19 | 681x524 | 54.7KB |
| 6 | figure_6.png | 34 | 1304x604 | 48.3KB |
| 7 | figure_7.png | 39 | 900x400 | 24.2KB |
