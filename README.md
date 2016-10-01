# Google open image download

A script for downloading and rescaling the [open image
dataset](https://github.com/openimages/dataset) in parallel. 

## setup

To install dependencies run

```
pip install -r requirements
```

Follow the instructions on the [open image data repo](https://github.com/openimages/dataset) to
get the list of image urls.

## usage

The two requirement arguments are `input` and `output`. Input is the csv file of urls from the open
image data set. Output is a directory where the scaled images will be saved. The saved images are
place in sub-directories for efficiency (the number of which is controlled by the `sub-dirs` arg).
The name of the saved image corresponds to the hex `ImageID` and can be used to look up labels in 
the open image dataset. 

Use `--help` to see the other optional args.
