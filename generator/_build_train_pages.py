"""One-off builder for the three HO layout project pages. Delete after use."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
sample = (root / "projects" / "19" / "index.html").read_text(encoding="utf-8")
nav = sample[sample.index("    <!-- Navigation -->") : sample.index("    <!-- Page Header -->")]
footer = sample[sample.index("    <!-- Footer -->") :]

pages = [
    {
        "folder": "5",
        "title": "HO Model Train Layout #3",
        "subtitle": "Green Hollow house, 2001-2007",
        "description": "20x20 foot layout I built in our Green Hollow house from 2001-2007.",
        "thumb": "assets/img/portfolio/thumbnails/5.jpg",
        "images": [
            "1.JPG", "2.JPG", "3.JPG", "4.JPG", "5.JPG", "6.JPG", "7.jpg",
            "8.jpg", "9.JPG", "10.JPG", "11.jpg", "12.JPG", "13.JPG", "14.JPG", "15.JPG",
        ],
    },
    {
        "folder": "14",
        "title": "HO Train Layout #1",
        "subtitle": "Nac, circa 1998",
        "description": "My first HO layout that I built when living in Nac circa 1998.",
        "thumb": "assets/img/portfolio/thumbnails/14.jpg",
        "images": [
            "1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg", "6.jpg", "7.jpg",
            "8.JPG", "9.JPG", "10.JPG",
        ],
    },
    {
        "folder": "15",
        "title": "HO Train Layout #2",
        "subtitle": "Plano, 1999",
        "description": "My next layout, after the first one I built in Nac, was more of a shelf/module style. I built it in 1999, when I moved to Plano and rented an apartment with a garage.",
        "thumb": "assets/img/portfolio/thumbnails/15.jpg",
        "images": ["1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg"],
    },
]

template = """<!DOCTYPE html>
<html lang="en">

<head>

    <!-- Global site tag (gtag.js) - Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=UA-174557574-1"></script>
    <script>
        window.dataLayer = window.dataLayer || [];

        function gtag() {{
            dataLayer.push(arguments);
        }}
        gtag('js', new Date());

        gtag('config', 'UA-174557574-1');
    </script>

    <title>{title}</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />

    <meta property="og:type" content="website" />
    <meta property="og:url" content="http://makeratplay.com/projects/{folder}/index.html" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:image" content="http://makeratplay.com/{thumb}" />
    <meta property="og:site_name" content="Maker At Play" />
    <meta property="og:locale" content="en_US">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:site" content="@MakerAtPlay1">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{description}">
    <meta name="twitter:image" content="http://makeratplay.com/{thumb}">

    <meta name="description" content="{description}" />
    <meta name="keywords" content="Model Train, HO scale, model railroad, Maker At Play" />
    <meta name="robots" content="index, follow" />
    <meta name="author" content="Michael Hawkins" />
    <meta name="p:domain_verify" content="7f14e2476e046f0fa6822fe6a41c9ad0" />

    <!-- Bootstrap core CSS -->
    <link href="/vendor/bootstrap/css/bootstrap.min.css" rel="stylesheet">

    <!-- Custom fonts for this template -->
    <script src="https://use.fontawesome.com/releases/v5.13.0/js/all.js" crossorigin="anonymous"></script>
    <link href='https://fonts.googleapis.com/css?family=Lora:400,700,400italic,700italic' rel='stylesheet'
        type='text/css'>
    <link
        href='https://fonts.googleapis.com/css?family=Open+Sans:300italic,400italic,600italic,700italic,800italic,400,300,600,700,800'
        rel='stylesheet' type='text/css'>

    <!-- Custom styles for this template -->
    <link href="../style.css" rel="stylesheet">

    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.0/js/bootstrap.bundle.min.js"></script>

</head>

<body>

{nav}
    <!-- Page Header -->
    <header class="masthead" style="background-image: url('masthead.jpg')">
        <div class="overlay"></div>
        <div class="container">
            <div class="row">
                <div class="col-lg-9 col-md-10 mx-auto">
                    <div class="post-heading">
                        <h1>{title}</h1>
                        <h2 class="subheading">{subtitle}</h2>
                        <span class="meta"></span>
                    </div>
                </div>
            </div>
        </div>
    </header>

    <!-- Post Content -->
    <article>
        <div class="container">
            <section class="py-5 container" style="margin-top: -80px">
                <div class="row">
                    <div class="col-lg-8 col-md-10 mx-auto">
                        <p>{description}</p>
                    </div>
                </div>
{images}
            </section>
        </div>
    </article>

    <hr>

{footer}"""

for page in pages:
    folder = root / "projects" / page["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / page["thumb"], folder / "masthead.jpg")
    image_html = []
    for index, name in enumerate(page["images"], start=1):
        url = f"/assets/img/portfolio/projects/{page['folder']}/{name}"
        alt = f"{page['title']}, photo {index}"
        image_html.append(
            f'                <a href="{url}" target="_blank"><img src="{url}" class="figure-img img-fluid rounded" alt="{alt}"></a>'
        )
    fields = dict(page)
    names = fields.pop("images")
    html = template.format(
        nav=nav,
        footer=footer,
        images="\n".join(image_html),
        **fields,
    )
    (folder / "index.html").write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {folder / 'index.html'}")
