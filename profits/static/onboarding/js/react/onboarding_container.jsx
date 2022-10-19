/*  global $, tasks, level, is_extension_installed
    level_1, level_2, level_3, uncompleted_task, ali_logo, alibaba_logo, ebay_logo
    setup_extension, connect_platform, import_products, get_assistance,
    send_product, process_first_order, create_bundle, process_100_orders,
    connect_sales_channel, create_supplement
*/

(function () {
    'use strict';

    const e = React.createElement;

    function getLevelImage(level) {
        switch (level) {
            case 1:
                return level_1;
            case 2:
                return level_2;
            case 3:
                return level_3;
            default:
                return '';
        }
    }

    function getLevelTitle(level) {
        switch (level) {
            case 1:
                return 'Beginner Checklist';
            case 2:
                return 'Intermediate Steps';
            case 3:
                return 'Advanced Steps';
            default:
                return '';
        }
    }

    function getTaskImage(task) {
        switch (task) {
            case 'Setup the Google Chrome Extension':
                return setup_extension;
            case 'Connect Your Store Platform':
                return connect_platform;
            case 'Import Products':
                return import_products;
            case 'Get Additional Assistance and Resources':
                return get_assistance;

            case 'Send a Product to Your Store':
                return send_product;
            case 'Process Your First Order':
                return process_first_order;
            case 'Create a Bundle':
                return create_bundle;
            case 'Process and Track 100 Orders':
                return process_100_orders;

            case 'Connect Aliexpress Account':
                return connect_sales_channel;
            case 'Create a Print on Demand Supplement':
                return create_supplement;
            case 'Process and Track 1000 Orders':
                return uncompleted_task;
            default:
                return uncompleted_task;
        }
    }

    function getTaskModalContent(task, isCompleted) {
        let image = uncompleted_task;
        let text = '';
        let buttonText = '';
        let url = '';

        switch (task) {
            case 'Setup the Google Chrome Extension':
                if (isCompleted) {
                    image = setup_extension;
                    text = 'Press the button “Install” and system will open the popup with installing extension.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Press the button “Install” and  system will open the page with installing extension.';
                    buttonText = 'Install Extension';
                    url = 'https://chrome.google.com/webstore/detail/shopified-app/aogkkekoinpipjlolpcicigndjlcpdcn';
                }
                break;
            case 'Connect Your Store Platform':
                if (isCompleted) {
                    image = connect_platform;
                    text = 'After you click the button “Choose Platform” the system will open a page for you with “Add Store” button. You need to choose which platform you want to connect first. If you don’t have any platform yet we can help you to create your first store.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'After you click the button “Choose Platform” the system will open a page for you with “Add Store” button. You need to choose which platform you want to connect first. If you don’t have any platform yet we can help you to create your first store.';
                    buttonText = 'Choose Platform';
                    url = '/';
                }
                break;
            case 'Import Products':
                if (isCompleted) {
                    image = import_products;
                    text = 'After you have installed the extension and connected your store, it\'s time to search for products. Let\'s look at the list of stores available to us and visit them to choose the best products for your business.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = '<div>After you have installed the extension and connected your store, it\'s time to search for products. Let\'s look at the list of stores available to us and visit them to choose the best products for your business.</div>' +
                        '<div class="partners-btn-group">' +
                        '<a href="https://www.aliexpress.com/" target="_blank" class="btn task-outline-btn"><img src="'+ ali_logo +'"/>AliExpress</a>' +
                        '<a href="https://www.alibaba.com/" target="_blank" class="btn task-outline-btn"><img src="'+ alibaba_logo +'"/>AliBaba</a>' +
                        '<a href="https://www.ebay.com/" target="_blank" class="btn task-outline-btn"><img src="'+ ebay_logo +'"/>eBay</a>' +
                        '</div>' +
                        '<a class="explore-link">Exlplore All Partners</a>';
                    buttonText = '/pages/content/source-import-products';
                    url = '';
                }
                break;
            case 'Get Additional Assistance and Resources':
                if (isCompleted) {
                    image = get_assistance;
                    text = 'You can go to our Help Center to look for the information you might need.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'You can go to our Help Center to look for the information you might need.';
                    buttonText = 'Visit Help Center';
                    url = 'https://learn.dropified.com/';
                }
                break;

            case 'Send a Product to Your Store':
                if (isCompleted) {
                    image = send_product;
                    text = 'Find products from suppliers and send them to your store via Dropified extension by clicking “Send to My Store”';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Find products from suppliers and send them to your store via Dropified extension by clicking “Send to My Store”.';
                    buttonText = 'Send to My Store';
                    url = '/product';
                }
                break;
            case 'Process Your First Order':
                if (isCompleted) {
                    image = process_first_order;
                    text = 'Once you receive your first order fulfill it using our website.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Once you receive your first order fulfill it using our website.';
                    buttonText = 'Check Products';
                    url = '/product';
                }
                break;
            case 'Create a Bundle':
                if (isCompleted) {
                    image = create_bundle;
                    text = 'Create your own unique bundles with us to sell more products with less effort.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Create your own unique bundles with us to sell more products with less effort.';
                    buttonText = 'Check Products';
                    url = '/product?store=c';
                }
                break;
            case 'Process and Track 100 Orders':
                if (isCompleted) {
                    image = process_100_orders;
                    text = 'Continue improving your sales using add-ons that we provide and reach 100 orders with us.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Continue improving your sales using add-ons that we provide and reach 100 orders with us.';
                    buttonText = '';
                    url = '';
                }
                break;

            case 'Connect Aliexpress Account':
                if (isCompleted) {
                    image = connect_sales_channel;
                    text = 'Connect your AliExpress account in Settings to bust up your selling experience.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Connect your AliExpress account in Settings to bust up your selling experience.';
                    buttonText = 'Connect AliExpress account';
                    url = '/aliexpress/oauth/';
                }
                break;
            case 'Create a Print on Demand Supplement':
                if (isCompleted) {
                    image = create_supplement;
                    text = 'Make your own customizable products without leaving the Dropified platform using Print on Demand feature.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Make your own customizable products without leaving the Dropified platform using Print on Demand feature.';
                    buttonText = 'Check Supplements';
                    url = '/supplements/';
                }
                break;
            case 'Process and Track 1000 Orders':
                if (isCompleted) {
                    image = process_100_orders;
                    text = 'Continue improving your sales using add-ons that we provide and reach 1000 orders with us.';
                    buttonText = 'Share on Social Media';
                    url = '';
                } else {
                    image = uncompleted_task;
                    text = 'Continue improving your sales using add-ons that we provide and reach 1000 orders with us.';
                    buttonText = '';
                    url = '';
                }
                break;
        }

        return {
            image: image,
            text: text,
            buttonText: buttonText,
            url: url,
        }
    }

    function TaskModal({ isShowingModal, handleCloseModal, updateTaskStatus, level,
                           task, isCompleted, image, text, buttonText, url }) {
        const [taskImage, setTaskImage] = React.useState(uncompleted_task);

        React.useEffect(() => {
            if (isShowingModal) {
                $('#task-modal').modal('show');
            } else {
                $('#task-modal').modal('hide');
            }
        }, [isShowingModal])

        React.useEffect(() => {
            if (image) {
                setTaskImage(image);
            }
        }, [image])

        $('#task-modal').on('hidden.bs.modal', function (e) {
            handleCloseModal();
        });

        function handleClick() {
            if (task === 'Get Additional Assistance and Resources') {
                localStorage.setItem('get_assistance', 'true');
                updateTaskStatus(task);
                setTaskImage(get_assistance)
            }
        }

        return (
            <div id="task-modal" className="modal fade" aria-hidden="true">
                <div className="modal-dialog" style={{maxWidth: '30%'}}>
                    <div className="modal-content">
                        <div className="modal-header">
                            <button type="button" className="close" data-dismiss="modal" aria-label="Close"><span
                                aria-hidden="true">&times;</span></button>
                        </div>
                        <div className="modal-body">
                            <div className="task">
                                <div className={isCompleted ? '' : 'uncompleted'}>
                                    <img src={taskImage} alt={task} />
                                </div>
                                <p>{task}</p>
                                <div className="info" dangerouslySetInnerHTML={{__html: text}}/>
                                {buttonText ?
                                    <React.Fragment>
                                    {!isCompleted &&
                                        // <a className="btn task-outline-btn">
                                        //     Share on Social Media
                                        //     <i className="fa fa-share-square-o" aria-hidden="true"/>
                                        // </a> :
                                        <a onClick={handleClick} href={url} target='_blank' className="btn task-primary-btn">{buttonText}</a>}
                                    </React.Fragment> : null}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    function LevelUpdateScreen({ level, changeLevel }) {
        return (
            <React.Fragment>
                <img src={getLevelImage(level)} alt='level' className='congratulation-img'/>
                <p className='congratulation-title'>Congratulations</p>
                <p className='congratulation-text'>
                    <span>You have completed all the tasks in order to start working with Dropified.</span>
                    {level !== 3 && <span>If you want to discover more benefits of Dropified, try the following tasks</span>}
                </p>
                {level === 3 ? <button className="btn onboarding-primary-btn" onClick={changeLevel}>View All Tasks</button>
                    : <button className="btn onboarding-primary-btn" onClick={changeLevel}>Try New Tasks</button>
                }
                <hr className="congratulation-hr"/>
                <a className="congratulation-share-link">Share to Social Media</a>
            </React.Fragment>
        );
    }

    class OnboardingContainer extends React.Component {
        constructor(props) {
            super(props);
            this.state = {
                level: level,
                isCompleted: false,
                isShowingModal: false,
                tasks: tasks,
                modalData: {
                    image: uncompleted_task,
                    text: '',
                    buttonText: ' ',
                    url: '',
                },
                viewAll: false,
            };
            this.onTaskClick = this.onTaskClick.bind(this);
            this.handleCloseModal = this.handleCloseModal.bind(this);
            this.changeLevel = this.changeLevel.bind(this);
            this.updateTaskStatus = this.updateTaskStatus.bind(this);
            this.updateExtensionStatus = this.updateExtensionStatus.bind(this);
            this.expandTasks = this.expandTasks.bind(this);
        }

        componentDidMount() {
            const { level, tasks } = this.state;
            let updatedTasks = Object.assign({}, tasks);
            if (level === 1) {
                updatedTasks['Setup the Google Chrome Extension'] = !!is_extension_installed;
                updatedTasks['Get Additional Assistance and Resources'] = !!localStorage.getItem('get_assistance');
            }
            const completedTasks = Object.keys(updatedTasks).filter(function (key) {
                return updatedTasks[key]
            })
            this.setState({
                tasks: updatedTasks,
                isCompleted: completedTasks.length === Object.keys(updatedTasks).length
            }, this.updateExtensionStatus)
        }

        updateExtensionStatus() {
            const {level, tasks} = this.state;
            if (level === 1) {
                if (!is_extension_installed) {
                    isExtensionReady().done(function () {
                        Cookies.set('ext_installed', 'true');

                        let updatedTasks = Object.assign({}, tasks);
                        updatedTasks['Setup the Google Chrome Extension'] = true;
                        const completedTasks = Object.keys(updatedTasks).filter(function (key) {
                            return updatedTasks[key]
                        })
                        this.setState({
                            tasks: updatedTasks,
                            isCompleted: completedTasks.length === Object.keys(updatedTasks).length
                        })
                    }.bind(this));
                }
            }
        }

        updateTaskStatus(task) {
            const { tasks } = this.state;
            let updatedTasks = Object.assign({}, tasks);
            updatedTasks[task] = true;

            const completedTasks = Object.keys(updatedTasks).filter(function (key) {
                return updatedTasks[key]
            })
            this.setState({
                tasks: updatedTasks,
                isCompleted: completedTasks.length === Object.keys(updatedTasks).length
            })
        }

        onTaskClick(task, isCompleted) {
            this.setState({
                isShowingModal: true,
                modalData: Object.assign(getTaskModalContent(task, isCompleted),
                    { task: task, isCompleted: isCompleted }),
            })
        }

        handleCloseModal() {
            this.setState({
                isShowingModal: false,
            })
        }

        changeLevel() {
            const { level } = this.state;
            $.ajax({
                url: api_url('user-level', 'profits'),
                type: 'POST',
                data: JSON.stringify({
                    'level': level + 1,
                }),
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                success: function (data) {
                    window.location.reload();
                },
                error: function (data) {
                    displayAjaxError('Level Update', data, true);
                }
            });
        }

        expandTasks(e) {
            e.preventDefault();
            const { viewAll } = this.state;
            this.setState({ viewAll: !viewAll });
        };

        render() {
            const { level, isCompleted, tasks, modalData, isShowingModal, viewAll } = this.state;
            var self = this;
            const completedTasks = Object.keys(tasks).filter(function(item) {
                return tasks[item];
            })
            const uncompletedTasks = Object.keys(tasks).filter(function(item) {
                return !tasks[item];
            })
            return (
                <React.Fragment>
                    <div className="tabs-container onboarding-container m-b">
                        <div className="tab-content">
                            <div id="tab-1" className="tab-pane active">
                                <div className="panel-body" style={{
                                    padding: '48px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    flexDirection: 'column',
                                }}>
                                    {level === 4 ?
                                        <React.Fragment>
                                            <div className="row" style={{ width: '100%' }}>
                                                <div className="col-xs-12 m-b-md onboarding-main-header"
                                                     style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'start' }}
                                                >
                                                    <div>
                                                        <p className="title">Build Your Business With Dropified</p>
                                                        <p>Below is a short checklist that we recommend in order to give
                                                            yourself the best chance of success!</p>
                                                    </div>
                                                    <div className="task-counter">
                                                        <span className="completed">{completedTasks.length}</span>
                                                        <span className="divider"> / </span>
                                                        {Object.keys(tasks).length}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="row" style={{ width: '100%' }}>
                                                {Object.keys(tasks).slice(0, 6).map(function (item, index) {
                                                    if (completedTasks.includes(item)) {
                                                        return (
                                                            <div className="col-xs-12 col-sm-6 col-md-4 col-lg-2 task"
                                                                 style={{ minHeight: '210px', marginTop: '15px' }}>
                                                                <div>
                                                                    <img src={getTaskImage(item)} alt='task-img'
                                                                         onClick={() => self.onTaskClick(item, true)}/>
                                                                </div>
                                                                <p>{item}</p>
                                                            </div>)
                                                    }
                                                    return (
                                                        <div className="col-xs-12 col-sm-6 col-md-4 col-lg-2 task"
                                                             style={{ minHeight: '210px', marginTop: '15px' }}>
                                                            <div className="uncompleted">
                                                                <img src={uncompleted_task} alt='task-img'
                                                                     onClick={() => self.onTaskClick(item, false)}/>
                                                            </div>
                                                            <p>{item}</p>
                                                        </div>)
                                                })}
                                            </div>
                                            <div className="row" style={{ width: '100%' }}>
                                                <div className="col-xs-12">
                                                    <a href="#" className="pull-right" style={{ fontSize: 16, fontWeight: 500, color: '#0085FF' }}
                                                       onClick={(e) => this.expandTasks(e)}>
                                                        {viewAll ? 'Hide' : 'View All'}
                                                    </a>
                                                </div>
                                            </div>
                                            <div className="row" style={{ display: viewAll ? 'block': 'none' }}>
                                                {Object.keys(tasks).slice(6).map(function (item, index) {
                                                    if (completedTasks.includes(item)) {
                                                        return (
                                                            <div className="col-xs-12 col-sm-6 col-md-4 col-lg-2 task"
                                                                 style={{ minHeight: '210px', marginTop: '15px' }}>
                                                                <div>
                                                                    <img src={getTaskImage(item)} alt='task-img'
                                                                         onClick={() => self.onTaskClick(item, true)}/>
                                                                </div>
                                                                <p>{item}</p>
                                                            </div>)
                                                    }
                                                    return (
                                                        <div className="col-xs-12 col-sm-6 col-md-4 col-lg-2 task"
                                                             style={{ minHeight: '210px', marginTop: '15px' }}>
                                                            <div className="uncompleted">
                                                                <img src={uncompleted_task} alt='task-img'
                                                                     onClick={() => self.onTaskClick(item, false)}/>
                                                            </div>
                                                            <p>{item}</p>
                                                        </div>)
                                                })}
                                            </div>
                                        </React.Fragment> :
                                        <React.Fragment>
                                            {isCompleted ?
                                                <LevelUpdateScreen level={level} changeLevel={this.changeLevel}/> :
                                                <React.Fragment>
                                                    <div className="onboarding-header row">
                                                        <div className="col-xs-4">
                                                            <p className="onboarding-title">{getLevelTitle(level)}</p>
                                                        </div>
                                                        <div className="col-xs-4">
                                                            <img src={getLevelImage(level)} alt='level'/>
                                                        </div>
                                                        <div className="col-xs-4 steps">
                                                            {completedTasks.map(function (item) {
                                                                return <div className="step completed"/>
                                                            })}
                                                            {uncompletedTasks.map(function (item) {
                                                                return <div className="step"/>
                                                            })}
                                                            <span>{completedTasks.length}/{Object.keys(tasks).length} Completed</span>
                                                        </div>
                                                    </div>
                                                    <hr className="onboarding-hr"/>
                                                    <div className="onboarding-body row">
                                                        {Object.keys(tasks).map(function (item) {
                                                            if (completedTasks.includes(item)) {
                                                                return (
                                                                    <div
                                                                        className={level === 3 ? 'col-xs-4 task' : 'col-xs-3 task'}>
                                                                        <div>
                                                                            <img src={getTaskImage(item)} alt='task-img'
                                                                                 onClick={() => self.onTaskClick(item, true)}/>
                                                                        </div>
                                                                        <p>{item}</p>
                                                                    </div>)
                                                            }
                                                            return (
                                                                <div
                                                                    className={level === 3 ? 'col-xs-4 task' : 'col-xs-3 task'}>
                                                                    <div className="uncompleted">
                                                                        <img src={uncompleted_task} alt='task-img'
                                                                             onClick={() => self.onTaskClick(item, false)}/>
                                                                    </div>
                                                                    <p>{item}</p>
                                                                </div>)
                                                        })}
                                                    </div>
                                                </React.Fragment>}
                                        </React.Fragment>}
                                </div>
                            </div>
                        </div>
                    </div>
                    <TaskModal
                        isShowingModal={isShowingModal}
                        handleCloseModal={this.handleCloseModal}
                        updateTaskStatus={this.updateTaskStatus}
                        level={level}
                        {...modalData}
                    />
                </React.Fragment>

            );
        }
    }

    const domContainer = document.querySelector('#onboarding-container');
    ReactDOM.render(<OnboardingContainer/>, domContainer);
}());
