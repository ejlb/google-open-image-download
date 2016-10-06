from __future__ import unicode_literals

import argparse
import csv
import errno
import logging
import multiprocessing
import os
import shutil
import time
import traceback

from PIL import Image

import requests
import six


def config_logger():
    logger = logging.getLogger('download')
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(process)d @ %(asctime)s (%(relativeCreated)d) '
                                  '%(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


def parse_args():
    parser = argparse.ArgumentParser(description='Download Google open image dataset.')

    parser.add_argument('--timeout', type=float, default=2.0,
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
    parser.add_argument('--force', default=False, action='store_true',
                        help='force download and overwrite local files')

    parser.add_argument('input', help='open image input csv')
    parser.add_argument('output', help='save directory')

    return parser.parse_args()


def unicode_dict_reader(f, **kwargs):
    csv_reader = csv.DictReader(f, **kwargs)
    for row in csv_reader:
        yield {key: value for key, value in six.iteritems(row)}


def safe_mkdir(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            log.exception()


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
    """ Aspect-ratio preserving scale such that the smallest dim is equal to `min_dim` """

    image = Image.open(content)

    # no scaling, keep images full size
    if min_dim == -1:
        return image

    # aspect-ratio preserving scale so that the smallest dimension is `min_dim`
    width, height = image.size
    scale_dimension = width if width < height else height
    scale_ratio = float(min_dim) / scale_dimension

    if scale_ratio == 1:
        return image

    return image.resize(
        (int(width * scale_ratio), int(height * scale_ratio)),
        Image.ANTIALIAS,
    )


def read_image(response, min_dim):
    """ Download response in chunks and convert to a scaled Image object """

    content = six.BytesIO()
    shutil.copyfileobj(response.raw, content)
    content.seek(0)

    return scale(content, min_dim)


def consumer(args, queue):
    """ Whilst the queue has images, download and save them """

    while queue.empty():
        time.sleep(0.1)  # give the queue a chance to populate

    while not queue.empty():
        code, url = queue.get(block=True, timeout=None)

        out_path = make_out_path(code, args.sub_dirs, args.output)

        if not args.force and os.path.exists(out_path):
            log.debug('skipping {}, already exists'.format(out_path))
            continue

        try:
            response = requests.get(url, stream=True, timeout=args.timeout)
            image = read_image(response, args.min_dim)
            image.save(out_path)
        except Exception:
            log.warning('error {}'.format(traceback.format_exc()))
        else:
            log.debug('saving {} to {}'.format(url, out_path))


def producer(args, queue):
    """ Populate the queue with image_id, url pairs. """

    with open(args.input) as f:
        for row in unicode_dict_reader(f):
            queue.put([row['ImageID'], row['OriginalURL']], block=True, timeout=None)
            log.debug('queue_size = {}'.format(queue.qsize()))

    queue.close()


log = config_logger()


if __name__ == '__main__':
    args = parse_args()
    log.debug(args)

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
