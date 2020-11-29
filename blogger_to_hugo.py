#!/usr/bin/env python

from __future__ import unicode_literals

import argparse
import difflib
import io
import logging
import os.path
import re
import sys
import xml.etree.cElementTree as ET

import pypandoc
import requests
import toml
from PIL import Image
from bs4 import BeautifulSoup as bs
from dateutil.parser import parse
from slugify import slugify


logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger()

NS = {
    'atom': 'http://www.w3.org/2005/Atom'
}
CATEGORY_KIND = 'http://schemas.google.com/g/2005#kind'
CATEGORY_TAG = 'http://www.blogger.com/atom/ns#'
TERM_POST = 'http://schemas.google.com/blogger/2008/kind#post'
MIN_IMAGE_TO_LINK_RATIO = 0.8

DEFAULT_THUMBNAIL_SIZE = (512, 384)
SIZE_RE = re.compile(r'(\d+)x(\d+)')


def create_required_directories(posts_dir_path):
    if os.path.exists(posts_dir_path):
        logger.error('Directory "%s" already exists', posts_dir_path)
        sys.exit(1)

    try:
        os.mkdir(posts_dir_path)
    except PermissionError:
        logger.error(
            'Permission denied when trying to create "%s"', posts_dir_path
        )
        sys.exit(1)
    os.mkdir(get_images_dir_path(posts_dir_path))
    os.mkdir(get_thumbnail_dir_path(posts_dir_path))


def get_images_dir_path(posts_dir_path):
    return os.path.join(posts_dir_path, 'images')


def get_thumbnail_dir_path(posts_dir_path):
    return os.path.join(get_images_dir_path(posts_dir_path), 'thumbnails')


def check_if_file_exists(path, original_path):
    if os.path.exists(path):
        logger.error('File %s -> %s already exists', original_path, path)
        sys.exit(1)


def download_and_save_image(image_src, original_src, fullimg_path):
    logger.info('Downloading %s', image_src)
    response = requests.get(image_src)
    if response.status_code != 200:
        logger.error(
            'Can\'t download image %s ; Status code %s',
            image_src, response.status_code
        )
        sys.exit(1)

    check_if_file_exists(fullimg_path, original_src)

    with io.open(fullimg_path, 'wb') as f:
        f.write(response.content)


def make_and_save_thumbnail(fullimg_path, thumb_path, thumb_size):
    logger.info('Making thumbnail for %s', fullimg_path)

    check_if_file_exists(thumb_path, fullimg_path)

    try:
        img = Image.open(fullimg_path)
        img.thumbnail(thumb_size, Image.BICUBIC)
        img.save(thumb_path)
    except ValueError:
        logger.error('Can\'t resize image %s', fullimg_path)
        sys.exit(1)


def get_post_entries(xml_root):
    result = []
    for entry in xml_root.findall('atom:entry', NS):
        for c in entry.findall('atom:category', NS):
            if (c.attrib['scheme'] == CATEGORY_KIND and
                    c.attrib['term'] == TERM_POST):
                result.append(entry)
                break
    return result


def guess_if_links_to_larger_img(a_tag, img_tag):
    ratio = difflib.SequenceMatcher(
        a=a_tag.attrs['href'], b=img_tag.attrs['src']
    ).ratio()
    return ratio > MIN_IMAGE_TO_LINK_RATIO


def get_src_resize_if_needed(img_attrs):
    def resize_if_needed(src, size_name, orig_size_name):
        if size_name in img_attrs and orig_size_name in img_attrs:
            size = img_attrs[size_name]
            orig_size = img_attrs[orig_size_name]
            return src.replace(
                '/s{}/'.format(size),
                '/s{}/'.format(orig_size)
            )
        return src

    src = img_attrs['src']

    src = resize_if_needed(src, 'height', 'data-original-height')
    src = resize_if_needed(src, 'width', 'data-original-width')
    return src


def image_path_to_content_path(img_path, options):
    relpath = os.path.relpath(img_path, options.output_folder)
    return os.path.join('..', relpath).replace('\\', '/')


def replace_images_with_downloaded(html, slug, options):
    images_dir_path = get_images_dir_path(options.output_folder)
    thumbnail_dir_path = get_thumbnail_dir_path(options.output_folder)

    for img in html.find_all('img'):
        if 'src' not in img.attrs:
            continue
        src = get_src_resize_if_needed(img.attrs)

        filename = slug + '-' + src[src.rfind('/') + 1:]
        fullimg_path = os.path.join(images_dir_path, filename)

        download_and_save_image(src, img['src'], fullimg_path)

        parent = img.find_parent()
        if parent.name == 'a' and guess_if_links_to_larger_img(parent, img):
            thumb_path = os.path.join('./', thumbnail_dir_path, filename)
            make_and_save_thumbnail(
                fullimg_path, thumb_path, options.thumbnail_size
            )

            a_tag = html.new_tag(
                'a', href=image_path_to_content_path(fullimg_path, options)
            )
            new_img = html.new_tag(
                'img', src=image_path_to_content_path(thumb_path, options)
            )
            a_tag.append(new_img)

            parent.replace_with(a_tag)
        else:
            new_img = html.new_tag(
                'img', src=image_path_to_content_path(fullimg_path, options)
            )
            img.replace_with(new_img)

    return html


def get_post_tags(post):
    result = []
    for c in post.findall('atom:category', NS):
        if c.attrib['scheme'] == CATEGORY_TAG:
            result.append(c.attrib['term'])
    return result


def process_post(post, options):
    title = post.find('atom:title', NS).text

    logger.info('Starting to process post: %s', title)

    published_str = post.find('atom:published', NS).text
    published = parse(published_str)
    published_date = '{:04}-{:02}-{:02}'.format(
        published.year, published.month, published.day
    )
    slug = '{}-{}'.format(published_date, slugify(title, to_lower=True))
    content = post.find('atom:content', NS).text
    author_name = post.find('atom:author', NS).find('atom:name', NS).text
    tags = get_post_tags(post)
    html = bs(content, 'html.parser')

    html = replace_images_with_downloaded(html, slug, options)

    mkd = pypandoc.convert_text(
        str(html), 'markdown_strict', format='html'
    )

    filename = os.path.join(options.output_folder, slug + '.md')

    with io.open(filename, 'w', encoding='utf-8') as f:
        f.write('+++\n{}\n+++\n{}\n'.format(toml.dumps({
            'title': title,
            'slug': slug,
            'published': published,
            'author': author_name,
            'tags': tags,
        }).strip(), mkd.strip()))

    logger.info('Saving into %s', filename)
    logger.info('')


def check_thumbnail_size(size):
    match = SIZE_RE.match(size)
    if match is None:
        raise argparse.ArgumentTypeError(
            'Thumbnail size must be in fallowing format INTEGERxINTEGER.'
            'Got "{}" instead'.format(size)
        )

    return int(match.group(1)), int(match.group(2))


def check_folder_path(folder_path):
    if os.path.exists(folder_path):
        raise argparse.ArgumentTypeError(
            'Output path "{}" already exists'.format(folder_path)
        )
    return folder_path


def check_blogger_xml(file_path):
    if not os.path.exists(file_path):
        raise argparse.ArgumentTypeError(
            'Such file "{}" does not exist'.format(file_path)
        )
    return file_path


def parser_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--thumbnail-size',
        metavar='WIDTHxHEIGHT',
        help='Thumbnail size "WIDTHxHEIGHT". Default {}x{}'.format(
            *DEFAULT_THUMBNAIL_SIZE
        ),
        type=check_thumbnail_size,
        required=False,
        default=DEFAULT_THUMBNAIL_SIZE
    )
    parser.add_argument(
        'blogger_file',
        metavar='BLOGGER_XML_FILE',
        help='Path to blogger xml file',
        type=check_blogger_xml
    )
    parser.add_argument(
        'output_folder',
        metavar='OUTPUT_FOLDER',
        help='Output folder path',
        type=check_folder_path,
    )

    return parser.parse_args()


def main():
    options = parser_arguments()

    create_required_directories(options.output_folder)

    try:
        xml_tree = ET.parse(options.blogger_file)
    except ET.ParseError:
        logger.error(
            'Can not parse "%s". Check if it is actually '
            'exported blogger\'s xml file', options.blogger_file
        )
        sys.exit(1)

    xml_root = xml_tree.getroot()

    posts = get_post_entries(xml_root)

    for post in posts:
        process_post(post, options)


if __name__ == "__main__":
    main()
