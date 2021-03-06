import argparse
import hashlib
import json
import logging
import os
import requests
from time import monotonic
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pathvalidate import sanitize_filename


logger = logging.getLogger('tululu')

CATEGORY_URL = 'http://tululu.org/l55/'
FOLDER_PATH = 'books'
IMAGES_PATH = 'images'
MAX_FILENAME_LENGHT = 50


def raise_for_status(response):
    try:
        response.raise_for_status()
        if response.status_code != 200: # А вдруг страницы не оказалось и случился редирект на главную?
            raise requests.HTTPError
    except (requests.HTTPError, requests.ConnectionError) as error:
        logger.error(f'{response.url}: {error}')

def get_hash(obj, algorithm='md5'):
    hash_obj = hashlib.new(algorithm)
    if not isinstance(obj, bytes):
        obj = obj.encode()
    hash_obj.update(obj)
    return hash_obj.hexdigest()

def download_txt(url, filename, folder):
    filename = sanitize_filename(filename)[:MAX_FILENAME_LENGHT]
    response = requests.get(url, allow_redirects=False)
    raise_for_status(response)

    book = response.text
    book_hash = get_hash(book)
    path = os.path.join(folder, f'{filename}_{book_hash}.txt')

    with open(path, 'w') as file:
        file.write(book)
    return path

def download_image(url, filename, folder):
    response = requests.get(url, allow_redirects=False)
    raise_for_status(response)

    img = response.content
    img_hash = get_hash(img)

    name, extension = os.path.splitext(filename)
    path = os.path.join(folder, f'{name}_{img_hash}{extension}')

    with open(path, 'wb') as file:
        file.write(img)
    return path

def parse_book_info(url):
    response = requests.get(url, allow_redirects=False)
    raise_for_status(response)

    soup = BeautifulSoup(response.text, 'lxml')
    title, author = map(str.strip, soup.select_one('h1').text.split('::'))
    book_txt_url = soup.select('.d_book tr a')[-3]
    book_image_url = soup.select_one('.d_book a img')
    comments = soup.select('.texts .black')
    genres = soup.select('span.d_book a')
    return {
        'title': title,
        'author': author,
        'book_txt_url': urljoin(url, book_txt_url['href']),
        'book_image_url': urljoin(url, book_image_url['src']),
        'book_image_name': book_image_url['src'].split('/')[-1],
        'comments': [comment.text for comment in comments],
        'genres': [genre.text for genre in genres]
    }

def get_total_pages(url=CATEGORY_URL):
    response = requests.get(url, allow_redirects=False)
    raise_for_status(response)
    soup = BeautifulSoup(response.text, 'lxml')
    end_page = soup.select('.npage')[-1].text
    return int(end_page)

def get_book_links(start_page, end_page, url=CATEGORY_URL):
    for page_number in range(start_page, end_page):
        page_url = urljoin(url, str(page_number))
        response = requests.get(page_url, allow_redirects=False)
        raise_for_status(response)
        soup = BeautifulSoup(response.text, 'lxml')
        books = soup.select('table.d_book div.bookimage a')
        
        for book in books:
            yield urljoin(url, book['href'])

def create_args_parser():
    parser = argparse.ArgumentParser(description='Парсер книг с сайта tululu.org')
    parser.add_argument('--start_page', help='Start page for parse', type=int, default=1)
    parser.add_argument('--end_page', help='End page for parse', type=int, default=2)
    parser.add_argument('--dest_folder', help='Path to save', default='.')
    parser.add_argument('--skip_imgs', help='Do not save images', action='store_true')
    parser.add_argument('--skip_txt', help='Do not save books', action='store_true')
    parser.add_argument('--json_path', help='Description path')
    return parser

def main():
    logging.basicConfig(level=logging.INFO, format=f'[%(levelname)s] %(message)s')
    parser = create_args_parser()
    args = parser.parse_args()

    start_page = args.start_page
    end_page=args.end_page

    total_pages = get_total_pages()
    end_page = min(end_page, total_pages)
        
    if end_page < start_page:
        logger.error('Ошибка в аргументах --start_page и --end_page')
        return

    logger.info('Download...')

    txt_path = os.path.join(args.dest_folder, FOLDER_PATH)
    img_path = os.path.join(args.dest_folder, IMAGES_PATH)
    os.makedirs(txt_path, exist_ok=True)
    os.makedirs(img_path, exist_ok=True)
    if args.json_path:
        os.makedirs(args.json_path, exist_ok=True)
        json_path = os.path.join(args.json_path, 'description.json')
    else:
        json_path = os.path.join(args.dest_folder, 'description.json')

    book_links = get_book_links(start_page, end_page)
    books_info = []

    time = monotonic()

    for book_link in book_links:
        try:
            book_info = parse_book_info(book_link)
            filename = book_info['title']
            imagename = book_info['book_image_name']
            txt_url = book_info['book_txt_url']
            image_url = book_info['book_image_url']

            description = {
                'title': filename,
                'author': book_info['author'],
                'comments': book_info['comments'],
                'genres': book_info['genres']
            }

            if not args.skip_txt:
                book_path_returned = download_txt(txt_url, filename, txt_path)
                description['book_src'] = book_path_returned

            if not args.skip_imgs:
                img_path_returned = download_image(image_url, imagename, img_path)
                description['img_src'] = img_path_returned

            books_info.append(description)
        except Exception as error:
            logger.error(error)

    with open(json_path, 'w') as file:
        json.dump(books_info, file, ensure_ascii=False)

    logger.info(f'Done in {monotonic() - time:.2f} sec.')


if __name__ == '__main__':
    main()
