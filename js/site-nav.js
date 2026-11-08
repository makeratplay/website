(function () {
  var script = document.currentScript;
  if (!script || !script.parentNode) return;

  var nav = document.createElement("nav");
  nav.className = "navbar navbar-expand-lg navbar-light fixed-top py-3";
  nav.id = "mainNav";
  nav.innerHTML = [
    '<div class="container">',
    '<a class="navbar-brand" href="/">Maker At Play</a>',
    '<button class="navbar-toggler navbar-toggler-right" type="button" aria-controls="navbarResponsive" aria-expanded="false" aria-label="Toggle navigation">',
    '<span class="navbar-toggler-icon"></span>',
    "</button>",
    '<div class="collapse navbar-collapse" id="navbarResponsive">',
    '<ul class="navbar-nav ml-auto my-2 my-lg-0">',
    '<li class="nav-item"><a class="nav-link" href="/">Home</a></li>',
    '<li class="nav-item"><a class="nav-link" href="/#portfolio">Projects</a></li>',
    '<li class="nav-item"><a class="nav-link" href="/workbench/">Workbench</a></li>',
    '<li class="nav-item"><a class="nav-link" href="/blog/">Blog</a></li>',
    '<li class="nav-item"><a class="nav-link" href="/about/">About</a></li>',
    '<li class="nav-item"><a class="nav-link" href="https://www.youtube.com/c/MakerAtPlay">YouTube</a></li>',
    "</ul>",
    "</div>",
    "</div>"
  ].join("");

  var button = nav.querySelector(".navbar-toggler");
  var collapse = nav.querySelector(".navbar-collapse");

  function setOpen(open) {
    collapse.classList.toggle("show", open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  button.addEventListener("click", function () {
    setOpen(!collapse.classList.contains("show"));
  });

  nav.addEventListener("click", function (event) {
    var link = event.target.closest("a.nav-link");
    if (!link) return;
    setOpen(false);

    var url;
    try {
      url = new URL(link.href, window.location.href);
    } catch (error) {
      return;
    }
    if (!url.hash || url.origin !== window.location.origin) return;

    var here = window.location.pathname.replace(/\/index\.html$/, "/");
    var there = url.pathname.replace(/\/index\.html$/, "/");
    if (here !== there) return;

    var target = document.getElementById(url.hash.slice(1));
    if (!target) return;
    event.preventDefault();
    var top = target.getBoundingClientRect().top + window.pageYOffset - 72;
    window.scrollTo({ top: top, behavior: "smooth" });
    if (window.history && window.history.pushState) {
      window.history.pushState(null, "", url.hash);
    }
  });

  script.parentNode.insertBefore(nav, script);
})();
