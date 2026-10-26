// Show a QR code for each Wi-Fi address of this laptop (usually there is one).

fetch('/api/connect')
  .then((res) => res.json())
  .then(({ phone_urls }) => {
    if (!phone_urls.length) {
      showError('This laptop is not connected to any Wi-Fi network or hotspot yet.');
      return;
    }
    phone_urls.forEach((url, i) => {
      $('codes').append(
        el('figure', {},
          el('img', { src: `/api/qr.svg?i=${i}`, alt: `QR code for ${url}`, width: '240', height: '240' }),
          el('figcaption', { className: 'item-title' }, url)
        )
      );
    });
  })
  .catch((e) => {
    console.error(e);
    showError('Could not load the phone address.');
  });
