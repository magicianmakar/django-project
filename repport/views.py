from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.template import Context, Template
# from django.conf import settings
from django.template.loader import get_template
from django.contrib.auth import logout as user_logout

from xhtml2pdf import pisa

from .models import *
from .forms import *
from app import settings

import httplib2, os, sys, urlparse, urllib2, re, json, requests

def init_project(project):
    overview_cat = Categorie(title='Content',
                             color='#5798a6',
                             algorithm_usage=23,
                             project=project)
    overview_cat.save()
    topics = [
        'Keyword Focus',
        'URL Structure',
        'Title Tags',
        'Meta Description Tags',
        'Meta Keywords',
        'Heading Tags',
        'Content',
        'Internal Linking & Anchor Text',
        'Image Names & Alt Tags',
        'NOFOLLOW Anchor Tags',
    ]

    for t in topics:
        Topic(title=t, categorie=overview_cat).save()

    indexing_cat = Categorie(title='Indexing',
                             color='#5e7f25',
                             algorithm_usage=12,
                             project=project)
    indexing_cat.save()
    topics = [
        'Page Exclusions',
        'Page Inclusions',
        'URL Redirects',
        'Duplicate Content',
        'Broken Links',
        'Code Validation',
        'Page Load Speed',
    ]

    for t in topics:
        Topic(title=t, categorie=indexing_cat).save()

    linking_cat = Categorie(title='Linking',
                             color='#db972d',
                             algorithm_usage=62,
                             project=project)
    linking_cat.save()
    topics = [
        'Inbound Followed Links',
        'Linking Root Domains',
        'Authority & Trust',
        'Social Media Mentions & Visibility',
        'Competitive Link Comparison'
    ]

    for t in topics:
        Topic(title=t, categorie=linking_cat).save()



def clone_project(src, project):
    # project.title = src.title
    # project.website = src.website
    # project.url = src.url
    # project.logo = src.logo
    # project.description = src.description
    # project.conclusion = src.conclusion

    template = src.template
    new_template = ProjectTemplate(
        title=template.title,
        report_template=template.report_template,
        report_style=template.report_style)

    new_template.save()

    project.template = new_template

    for c in src.categorie_set.all().all().order_by('id'):
        cat = Categorie(
            title=c.title,
            content_analysis=c.content_analysis,
            content_score=c.content_score,
            color=c.color,
            algorithm_usage=c.algorithm_usage,
            project=project)
        cat.save()

        for t in c.topic_set.all().order_by('id'):
            topic = Topic(
                title=t.title,
                score=t.score,
                action_item=t.action_item,
                analysis=t.analysis,
                recommendations=t.recommendations,
                guidelines=t.guidelines,
                action_description=t.action_description,
                categorie=cat,
            )
            topic.save()


@login_required
def index(request):
    # init_project()

    projects = Project.objects.all()
    templates = ProjectTemplate.objects.all()

    return render(request, 'index.html', {
        'projects': projects,
        'templates': templates
    })

@login_required
def project_view(request, project_id):
    project = get_object_or_404(Project, pk=project_id)

    return render(request, 'project/settings.html', {
        'project': project,
        'clist': 'settings',
        'breadcrumbs': [project.title]
    })

@login_required
def category_view(request, cat_id):
    category = get_object_or_404(Categorie, pk=cat_id)

    return render(request, 'project/category.html', {
        'project': category.project,
        'category': category,
        'clist': category.id,
        'breadcrumbs': [{'title': category.project.title, 'url': '/project/%d'%category.project.id}, '%s Category '%category.title]
    })

@login_required
def topic_view(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    category = topic.categorie

    return render(request, 'project/topic.html', {
        'project': category.project,
        'category': category,
        'topic': topic,
        'clist': category.id,
        'tlist': topic.id,
        'breadcrumbs': [
            {'title': category.project.title, 'url': '/project/%d'%category.project.id},
            {'title': '%s Category '%category.title, 'url': '/category/%d'%category.id},
            topic.title]
    })

@login_required
def api(request, target):
    data = request.POST
    if target == 'project':
        project = get_object_or_404(Project, pk=data.get('project'))
        project.title = data.get('title')
        project.website = data.get('website')
        project.url = data.get('url')
        project.logo = data.get('logo')
        project.description = data.get('description', '')
        project.conclusion = data.get('conclusion')
        project.save()
        return HttpResponse('ok')

    if target == 'category':
        category = get_object_or_404(Categorie, pk=data.get('category'))
        category.title = data.get('title')
        category.algorithm_usage = data.get('algorithm')
        category.color = data.get('color')
        category.content_analysis = data.get('content_analysis')
        category.content_score = data.get('content_score')
        category.save()
        return HttpResponse('ok')

    if target == 'topic':
        topic = get_object_or_404(Topic, pk=data.get('topic'))
        topic.title = data.get('title')
        topic.score = data.get('score')
        topic.analysis = data.get('analysis')
        topic.recommendations = data.get('recommendations')
        topic.guidelines = data.get('guidelines')
        topic.action_description = data.get('action_description')
        topic.save()
        return HttpResponse('ok')

    if target == 'score':
        topic = get_object_or_404(Topic, pk=data.get('topic'))
        topic.score = data.get('score')
        topic.save()
        return HttpResponse('ok')

    if target == 'action-item':
        topic = get_object_or_404(Topic, pk=data.get('topic'))
        topic.action_item = data.get('action')
        topic.save()
        return HttpResponse('ok')

    if target == 'template':
        template = get_object_or_404(ProjectTemplate, pk=data.get('template'))
        template.report_style = data.get('report_style')
        template.report_template = data.get('report_template')
        template.save()
        return HttpResponse('ok')

    if target == 'add-project':
        template = get_object_or_404(ProjectTemplate, pk=data.get('template'))
        new_template = ProjectTemplate(
            title=template.title,
            report_template=template.report_template,
            report_style=template.report_style)

        new_template.save()

        project = Project(title=data.get('title'), template=new_template)
        project.save()

        init_project(project)

        return HttpResponse('/project/%d'%project.id)

    if target == 'clone-project':
        src = get_object_or_404(Project, pk=data.get('src-project'))
        project = Project(title=data.get('title'), template=src.template)
        project.save()

        clone_project(src, project)

        return HttpResponse('/project/%d'%project.id)

    if target == 'metrics-edit':
        template = get_object_or_404(Metric, pk=data.get('metric'))
        template.value = data.get('value')
        template.save()
        return HttpResponse('ok')

    if target == 'metrics-add':
        import re
        if not re.match('^[a-z][a-z0-9_-]+$', data.get('metric-name')):
            return HttpResponse('Error: Metric name should contains only litters and numbers and _ and should start with a letter.')

        project = get_object_or_404(Project, pk=data.get('project'))
        metric = Metric(name=data.get('metric-name'),
            description=data.get('metric-description'),
            value=data.get('metric-value'),
            project=project)
        metric.save()

        return redirect('/project/metrics/%d'%project.id)


    return HttpResponse('error')

@login_required
def scorecard_view(request, project_id):
    project = get_object_or_404(Project, pk=project_id)

    return render(request, 'project/scorecard.html', {
        'project': project,
        'clist': 'scorecard',
        'breadcrumbs': [{'title': project.title, 'url': '/project/%d'%project.id}, 'Scorecard']
    })

@login_required
def preview_project(request, project_id, for_pdf=False):
    project = get_object_or_404(Project, pk=project_id)
    tpl = project.template

    template = get_template('project/preview.html')
    ctx = {
        'project': project,
        'template': tpl,
        'metrics': project.get_metrics('all'),
        'pdf': for_pdf,
        'clist': 'preview',
        'breadcrumbs': [{'title': project.title, 'url': '/project/%d'%project.id}, 'Preview']
    }

    context = Context(ctx)
    repport_html = template.render(context)

    if for_pdf:
        return repport_html
    else:
        return HttpResponse(repport_html)

# Convert HTML URIs to absolute system paths so xhtml2pdf can access those resources
def link_callback(uri, rel):

    # use short variable names
    sUrl  = settings.STATIC_URL      # Typically /static/
    sRoot = settings.STATIC_ROOT    # Typically /home/userX/project_static/
    mUrl  = settings.MEDIA_URL       # Typically /static/media/
    mRoot = settings.MEDIA_ROOT     # Typically /home/userX/project_static/media/

    # convert URIs to absolute system paths
    if uri.startswith(mUrl):
        path = os.path.join(settings.BASE_DIR2, uri)
    elif uri.startswith(sUrl):
        path = os.path.join(settings.BASE_DIR2, (uri[1:] if uri[0] == '/' else uri))
    else:
        return uri

    # make sure that file exists
    if not os.path.isfile(path):
            print (
                    '%s: media URI must start with %s or %s' % \
                    (uri, sUrl, mUrl))

    return path

@login_required
def generate_pdf(request, project_id):
    project = get_object_or_404(Project, pk=project_id)

    # Write PDF to file
    file = open(os.path.join(settings.MEDIA_ROOT, 'test.pdf'), "w+b")
    pisaStatus = pisa.CreatePDF(preview_project(request, project_id, True), dest=file, debug=10, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    file.seek(0)
    pdf = file.read()
    file.close()            # Don't forget to close the file handle
    return HttpResponse(pdf, content_type='application/pdf')

@login_required
def project_templates(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    tpl = project.template

    ctx = {
        'project': project,
        'template': tpl,
        'clist': 'templates',
        'breadcrumbs': [{'title': project.title, 'url': '/project/%d'%project.id}, 'Templates']
    }

    return render(request, "project/templates.html", ctx)

def project_metrics(request, project_id):
    project = get_object_or_404(Project, pk=project_id)

    if request.GET.get('update'):
        project.update_api_metrics(request.GET.get('only'))
    if request.GET.get('crawler'):
        project.update_crawler_metrics(request.GET.get('crawler'))
        return HttpResponse('ok')

    if not request.user.is_authenticated:
        return HttpResponseRedirect('/accounts/login/?next=%s'%request.META.get('PATH_INFO'))

    metrics = project.metric_set.all()
    metrics_moz = []
    metrics_google = []
    metrics_sharecount = []
    crawler_metrics = []
    metrics_user = []

    for i in metrics:
        if i.name.startswith('api_google_'):
            metrics_google.append(i)
        elif i.name.startswith('api_sharecount'):
            metrics_sharecount.append(i)
        elif i.name.startswith('api_crawler'):
            crawler_metrics.append(i)
        elif i.name.startswith('api_'):
            metrics_moz.append(i)
        else:
            metrics_user.append(i)

    if len(metrics_moz) == 0:
        data =  project.get_metrics('moz')
        for i in data:
            metrics_moz.append({
                'name': i,
                'value': data[i]
            })

    if len(metrics_google) == 0:
        data =  project.get_metrics('google')
        for i in data:
            metrics_google.append({
                'name': i,
                'value': data[i]
            })

    if len(metrics_sharecount) == 0:
        data =  project.get_metrics('sharecount')
        for i in data:
            metrics_sharecount.append({
                'name': i,
                'value': data[i]
            })

    if len(crawler_metrics) == 0:
        data =  project.get_metrics('crawler')
        for i in data:
            crawler_metrics.append({
                'name': i,
                'value': data[i]
            })

    metrics = project.metric_set.all()

    crawler_metrics_status = 0

    try:
        r = requests.get('%s/get'%settings.CRAWLER_API_BASE, {
            'url': project.url
        })
    except:
        crawler_metrics_status = -1
        pass

    try:
        crawler_metrics_status = r.json()['status']
    except:
        pass

    ctx = {
        'project': project,
        'metrics': metrics,
        'metrics_moz': metrics_moz,
        'metrics_google': metrics_google,
        'metrics_sharecount': metrics_sharecount,
        'crawler_metrics': crawler_metrics,
        'metrics_user': metrics_user,
        'crawler_metrics_status': crawler_metrics_status,
        'CRAWLER_API_BASE': settings.CRAWLER_API_BASE,
        'clist': 'metrics',
        'breadcrumbs': [{'title': project.title, 'url': '/project/%d'%project.id}, 'Metrics']

    }

    return render(request, "project/metrics.html", ctx)

@login_required
def project_explorer(request, project_id, etype='links'):
    from app.flask_app import db, Website, WebsiteLink, WebsiteImage

    project = get_object_or_404(Project, pk=project_id)

    ctx = {
        'project': project,
        'clist': 'explorer',
        'breadcrumbs': [{'title': project.title, 'url': '/project/%d'%project.id},
                        {'title': 'Explorer', 'url': '/project/%d/explorer'%project.id}]
    }

    try:
        website = Website.query.filter_by(url=project.url).first()
    except Exception as e:
        website = None
        db.session.remove()
        etype = 'error'
        ctx['error'] = str(e)


    if not website and etype != 'error':
        etype = 'notfound'

    if etype == 'links':
        ctx['links_count'] = website.links.count()
        ctx['links'] = website.links.all()

        ctx['breadcrumbs'].append('Links')

    if etype == 'titles':
        titles = []
        links = db.session.query(WebsiteLink, db.func.count(WebsiteLink.title)) \
                          .filter(WebsiteLink.website==website) \
                          .group_by(WebsiteLink.title) \
                          .all()

        for i in links:
            link, count = i
            titles.append({
                'link': link,
                'count': count
            })

        ctx['titles'] = titles
        ctx['breadcrumbs'].append('Titles')

    if etype == 'description':
        descriptions = []
        links = db.session.query(WebsiteLink, db.func.count(WebsiteLink.description)) \
                          .filter(WebsiteLink.website==website) \
                          .group_by(WebsiteLink.description) \
                          .all()

        for i in links:
            link, count = i
            descriptions.append({
                'link': link,
                'count': count
            })

        ctx['descriptions'] = descriptions
        ctx['breadcrumbs'].append('Meta Descriptions')

    if etype == 'images':
        images = []
        links = db.session.query(WebsiteImage, db.func.count(WebsiteImage.id)) \
                          .filter(WebsiteImage.website_link.has(website=website)) \
                          .group_by(WebsiteImage.src) \
                          .all()

        for i in links:
            image, count = i
            images.append({
                'image': image,
                'count': count
            })

        ctx['images'] = images
        ctx['breadcrumbs'].append('Images')

    if etype != 'error':
        db.session.remove()

    return render(request, "project/explorer/%s.html"%etype, ctx)

@login_required
def logout(request):
    user_logout(request)
    return redirect('index')

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            return HttpResponseRedirect("/")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {
        'form': form,
    })
