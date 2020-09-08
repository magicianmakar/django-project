from calendar import monthrange


def millify(n):
    return round(float(n), 2)


def get_days_in_month(dt):
    return monthrange(dt.year, dt.month)[1]


def sort_sku_data(all_sku, sku_data, all_title, all_link):
    if type(sku_data[0]) == int:
        data = {}
        for i, item in enumerate(sku_data):
            data[all_sku[i]] = {
                'data': item,
                'title': all_title[i],
                'link': all_link[i]
            }
        sku_data.sort(reverse=True)
        sorted_sku = []
        sorted_title = []
        sorted_link = []
        for item in sku_data:
            for key, val in data.items():
                if val['data'] == item:
                    sorted_sku.append(key)
                    sorted_title.append(val['title'])
                    sorted_link.append(val['link'])
                    data.pop(key)
                    break
        return sorted_sku, sku_data, sorted_title, sorted_link
    else:
        interim_data = [sum(item) for item in sku_data]
        interim_data_sorted = sorted(interim_data, reverse=True)
        data = {}
        for i, item in enumerate(interim_data):
            data[all_sku[i]] = {
                'data': item,
                'title': all_title[i],
                'link': all_link[i]
            }
        sorted_sku = []
        sorted_title = []
        sorted_link = []
        for item in interim_data_sorted:
            for key, val in data.items():
                if val['data'] == item:
                    sorted_sku.append(key)
                    sorted_title.append(val['title'])
                    sorted_link.append(val['link'])
                    data.pop(key)
                    break
        data_dict = {}
        for i, item in enumerate(interim_data):
            data_dict[item] = sku_data[i]
        sorted_data = []
        for item in interim_data_sorted:
            for key, val in data_dict.items():
                if key == item:
                    sorted_data.append(val)
                    data_dict.pop(key)
                    break
        return sorted_sku, sorted_data, sorted_title, sorted_link


def sort_seller(obj):
    return obj['total_sales']


def sort_items(obj):
    return obj['q']
