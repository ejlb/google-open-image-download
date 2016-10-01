from __future__ import print_function

import argparse
import csv
import errno
import multiprocessing
import traceback
import os
import shutil
import StringIO

import requests

from PIL import Image

# docs
# py2 / py3
# progress bar
# logging
# flake8
# split ?

def parse_args():
    parser = argparse.ArgumentParser(description='Download Google open image dataset.')

    parser.add_argument('--timeout', type=int, default=2,
                        help='image download timeout')
    parser.add_argument('--queue-size', type=int, default=1000,
                        help='maximum image url queue size')
    parser.add_argument('--consumers', type=int, default=5,
                        help='number of download workers')
    parser.add_argument('--min-dim', type=int, default=256,
                        help='smallest dimension for the aspect ratio preserving scale'
                             '(-1 for no scale)')
    parser.add_argument('--sub-dirs', type=int, default=1000,
                        help='number of directories to split downloads over')
    parser.add_argument('--quiet', default=False, action='store_true',
                        help='disable logging')
    parser.add_argument('--force', default=False, action='store_true',
                        help='force download and overwrite local files')

    parser.add_argument('input', help='open image input csv')
    parser.add_argument('output', help='save directory')

    return parser.parse_args()


def safe_mkdir(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def make_out_path(code, sub_dirs, out_dir):
    # convert hex string identifier to integer
    int_code = int(code, 16)

    # choose a sub-directory to store image in
    sub_dir = str(int_code % (sub_dirs - 1))

    # make the sub directory if it does not exist
    path = os.path.join(out_dir, sub_dir)
    safe_mkdir(path)

    return os.path.join(path, code + '.jpg')


def scale(content, min_dim):
    image = Image.open(content)

    if min_dim == -1:
        return image

    width, height = image.size
    scale_dimension = width if width < height else height
    scale_ratio = float(min_dim) / scale_dimension

    if scale_ratio == 1:
        return image

    return image.resize(
        (int(width * scale_ratio), int(height * scale_ratio)),
        Image.ANTIALIAS,
    )


def write_response(response, out_path, min_dim):
    content = StringIO.StringIO()

    shutil.copyfileobj(response.raw, content)
    content.seek(0)

    image = scale(content, min_dim)
    image.save(out_path)


def consumer(args, queue):
    while not queue.empty():
        code, url = queue.get(block=True, timeout=None)

        out_path = make_out_path(code, args.sub_dirs, args.output)

        if not args.force and os.path.exists(out_path):
            print('skip')
            continue

        if not args.quiet:
            print(url, out_path)

        try:
            response = requests.get(url, stream=True, timeout=args.timeout)
            write_response(response, out_path, args.min_dim)
        except Exception as e:
            print('download error', e)
            traceback.print_exc()


def producer(args, queue):
    f = open(args.input)

    for row in csv.DictReader(f):
        queue.put([row['ImageID'], row['OriginalURL']], block=True, timeout=None)

    queue.close()


if __name__ == '__main__':
    args = parse_args()

    queue = multiprocessing.Queue(args.queue_size)

    processes = [
        multiprocessing.Process(target=producer, args=(args, queue))
    ]

    for i in range(args.consumers):
        processes.append(multiprocessing.Process(target=consumer, args=(args, queue)))

    for p in processes:
        p.start()

    for p in processes:
        p.join()
