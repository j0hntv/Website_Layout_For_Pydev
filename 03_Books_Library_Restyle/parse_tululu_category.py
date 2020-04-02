import argparse
import json
import os
import requests
from time import monotonic
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pathvalidate import sanitize_filename


BASE_URL = 'http://tululu.org'
CATEGORY_URL = 'http://tululu.org/l55/'
FOLDER_PATH = 'books/'
IMAGES_PATH = 'images/'
MAX_FILENAME_LENGHT = 50


def download_txt(url, filename, folder):
    response = requests.get(url, allow_redirects=False)
    response.raise_for_status()
    if not response.status_code == 200:
        return

    path = os.path.join(folder, f'{sanitize_filename(filename)[:MAX_FILENAME_LENGHT]}.txt')

    with open(path, 'w') as file:
        file.write(response.text)
    return path

def download_image(url, filename, folder):
    response = requests.get(url, allow_redirects=False)
    response.raise_for_status()
    if not response.status_code == 200:
        return

    path = os.path.join(folder, filename)

    with open(path, 'wb') as file:
        file.write(response.content)
    return path

def parse_book_info(url):
    response = requests.get(url, allow_redirects=False)
    response.raise_for_status()
    if not response.status_code == 200:
        return

    soup = BeautifulSoup(response.text, 'lxml')
    title, author = map(str.strip, soup.select_one('h1').text.split('::'))
    book_txt_url = soup.select_one('.d_book a[title*="скачать книгу txt"]')
    book_image_url = soup.select_one('.d_book a img')
    comments = soup.select('.texts .black')
    genres = soup.select('span.d_book a')

    if book_txt_url:
        return {
            'title': title,
            'author': author,
            'book_txt_url': urljoin(BASE_URL, book_txt_url['href']),
            'book_image_url': urljoin(BASE_URL, book_image_url['src']),
            'book_image_name': book_image_url['src'].split('/')[-1],
            'comments': [comment.text for comment in comments],
            'genres': [genre.text for genre in genres]
        }

def get_total_pages(url=CATEGORY_URL):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'lxml')
    end_page = soup.select('.npage')[-1].text
    return int(end_page)

def get_book_links(start_page, end_page, url=CATEGORY_URL):
    total_pages = get_total_pages()
    if end_page > total_pages:
        end_page = total_pages

    if end_page < start_page:
        raise IndexError

    for page_number in range(start_page, end_page):
        page_url = urljoin(url, str(page_number))
        response = requests.get(page_url)
        response.raise_for_status()
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
    parser = create_args_parser()
    args = parser.parse_args()

    print('Download...')

    txt_path = os.path.join(args.dest_folder, FOLDER_PATH)
    img_path = os.path.join(args.dest_folder, IMAGES_PATH)
    os.makedirs(txt_path, exist_ok=True)
    os.makedirs(img_path, exist_ok=True)
    if args.json_path:
        os.makedirs(args.json_path, exist_ok=True)
        json_path = os.path.join(args.json_path, 'description.json')
    else:
        json_path = os.path.join(args.dest_folder, 'description.json')

    
    book_links = get_book_links(start_page=args.start_page, end_page=args.end_page)
    books_info = []

    time = monotonic()

    for book_link in book_links:
        book_info = parse_book_info(book_link)
        if not book_info:
            continue

        filename = book_info['title']
        imagename = book_info['book_image_name']
        txt_url = book_info['book_txt_url']
        image_url = book_info['book_image_url']

        if not args.skip_txt:
            download_txt(txt_url, filename, txt_path)

        if not args.skip_imgs:
            download_image(image_url, imagename, img_path)

        description = {
            'title': filename,
            'author': book_info['author'],
            'img_src': os.path.join(img_path, imagename),
            'book_path': os.path.join(txt_path, filename),
            'comments': book_info['comments'],
            'genres': book_info['genres']
        }

        books_info.append(description)

    with open(json_path, 'w') as file:
        json.dump(books_info, file, ensure_ascii=False)

    print(f'Done in {monotonic() - time:.2f} sec.')


if __name__ == '__main__':
    try:
        main()
    except IndexError:
        print('[*] Ошибка в аргументах --start_page и --end_page')