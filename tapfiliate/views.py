from django.shortcuts import render


def conversion(request):

    return render(request, 'tapfiliate/conversion.html', {})
