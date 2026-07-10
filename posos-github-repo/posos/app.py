import json, os, shutil, tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
from .db import Database
from .security import hash_pin, verify_pin

DATA_DIR=Path(os.environ.get('POSOS_DATA_DIR','/var/lib/posos' if os.geteuid()==0 else Path.home()/'.local/share/posos'))
DB=Database(DATA_DIR/'posos.db')


def money(c): return f'${c/100:.2f}'
def cents(s):
    return int(round(float(s.replace('$','').strip())*100))

class POSOS(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('POSOS'); self.geometry('1024x700'); self.minsize(800,600)
        self.current_user=None; self.cart={}; self.barcode_buffer=''
        self.option_add('*Font',('DejaVu Sans',12)); self.protocol('WM_DELETE_WINDOW', self.manager_exit)
        try: self.attributes('-fullscreen', os.environ.get('POSOS_WINDOWED')!='1')
        except Exception: pass
        if DB.employee_count()==0: self.first_run()
        self.login_screen()

    def clear(self):
        for w in self.winfo_children(): w.destroy()

    def first_run(self):
        messagebox.showinfo('POSOS Setup','Create the first manager account. This PIN controls manager settings.')
        while True:
            name=simpledialog.askstring('Manager setup','Manager name:',parent=self)
            pin=simpledialog.askstring('Manager setup','Create a 4–12 digit manager PIN:',show='•',parent=self)
            confirm=simpledialog.askstring('Manager setup','Confirm manager PIN:',show='•',parent=self)
            if name and pin==confirm:
                try: DB.add_employee(name.strip(),hash_pin(pin),'manager'); break
                except ValueError as e: messagebox.showerror('Invalid PIN',str(e))
            else: messagebox.showerror('Setup incomplete','Name is required and both PIN entries must match.')

    def login_screen(self):
        self.clear(); f=ttk.Frame(self,padding=40); f.pack(expand=True)
        ttk.Label(f,text='POSOS',font=('DejaVu Sans',34,'bold')).pack(pady=20)
        ttk.Label(f,text='Employee PIN').pack(); v=tk.StringVar(); e=ttk.Entry(f,textvariable=v,show='•',font=('DejaVu Sans',24),justify='center'); e.pack(pady=15); e.focus()
        def go(*_):
            for emp in DB.employee_by_pin_candidates():
                if verify_pin(v.get(),emp['pin_hash']): self.current_user=emp; self.register_screen(); return
            v.set(''); messagebox.showerror('Login failed','Incorrect or disabled employee PIN.')
        ttk.Button(f,text='Sign In',command=go).pack(fill='x'); e.bind('<Return>',go)

    def register_screen(self):
        self.clear(); self.cart={}
        top=ttk.Frame(self,padding=8); top.pack(fill='x')
        ttk.Label(top,text=f"POSOS — {self.current_user['name']}",font=('DejaVu Sans',18,'bold')).pack(side='left')
        ttk.Button(top,text='Log out',command=self.login_screen).pack(side='right')
        if self.current_user['role']=='manager': ttk.Button(top,text='Manager',command=self.manager_screen).pack(side='right',padx=8)
        body=ttk.Panedwindow(self,orient='horizontal'); body.pack(fill='both',expand=True,padx=8,pady=8)
        left=ttk.Frame(body); right=ttk.Frame(body); body.add(left,weight=3); body.add(right,weight=2)
        search=tk.StringVar(); se=ttk.Entry(left,textvariable=search,font=('DejaVu Sans',18)); se.pack(fill='x',pady=(0,8)); se.focus()
        grid=ttk.Frame(left); grid.pack(fill='both',expand=True)
        def refresh(*_):
            for w in grid.winfo_children(): w.destroy()
            q=search.get().lower().strip(); items=[i for i in DB.items(True) if q in i['name'].lower() or q in (i['barcode'] or '').lower()]
            for idx,item in enumerate(items[:60]):
                ttk.Button(grid,text=f"{item['name']}\n{money(item['price_cents'])}",command=lambda i=item:self.add_item(i)).grid(row=idx//4,column=idx%4,sticky='nsew',padx=3,pady=3)
            for c in range(4): grid.columnconfigure(c,weight=1)
        search.trace_add('write',refresh); refresh()
        se.bind('<Return>',lambda _:(self.scan_or_search(search.get()),search.set('')))
        self.cart_tree=ttk.Treeview(right,columns=('qty','price','total'),show='tree headings',height=18)
        self.cart_tree.heading('#0',text='Item'); self.cart_tree.heading('qty',text='Qty'); self.cart_tree.heading('price',text='Price'); self.cart_tree.heading('total',text='Total')
        self.cart_tree.pack(fill='both',expand=True)
        self.total_label=ttk.Label(right,text='Total: $0.00',font=('DejaVu Sans',28,'bold')); self.total_label.pack(pady=12)
        buttons=ttk.Frame(right); buttons.pack(fill='x')
        ttk.Button(buttons,text='Remove',command=self.remove_selected).pack(side='left',expand=True,fill='x')
        ttk.Button(buttons,text='Clear',command=lambda:(self.cart.clear(),self.refresh_cart())).pack(side='left',expand=True,fill='x')
        ttk.Button(right,text='CASH PAYMENT',command=self.cash_payment).pack(fill='x',pady=8,ipady=12)

    def scan_or_search(self,text):
        item=DB.item_by_barcode(text.strip())
        if item: self.add_item(item)

    def add_item(self,item):
        key=item['id']; self.cart.setdefault(key,{'id':key,'name':item['name'],'price_cents':item['price_cents'],'qty':0}); self.cart[key]['qty']+=1; self.refresh_cart()
    def refresh_cart(self):
        for x in self.cart_tree.get_children(): self.cart_tree.delete(x)
        total=0
        for k,l in self.cart.items():
            line=l['qty']*l['price_cents']; total+=line; self.cart_tree.insert('', 'end', iid=str(k), text=l['name'], values=(l['qty'],money(l['price_cents']),money(line)))
        self.total_label.config(text=f'Total: {money(total)}')
    def remove_selected(self):
        for iid in self.cart_tree.selection(): self.cart.pop(int(iid),None)
        self.refresh_cart()
    def cash_payment(self):
        if not self.cart: return
        total=sum(l['qty']*l['price_cents'] for l in self.cart.values())
        raw=simpledialog.askstring('Cash payment',f'Total: {money(total)}\nCash received:')
        try: cash=cents(raw); assert cash>=total
        except Exception: messagebox.showerror('Payment','Cash amount must be at least the total.'); return
        change=cash-total; sid=DB.complete_sale(self.current_user['id'],list(self.cart.values()),total,cash,change)
        messagebox.showinfo('Sale complete',f'Sale #{sid}\nChange: {money(change)}')
        self.cart={}; self.refresh_cart()

    def manager_screen(self):
        if self.current_user['role']!='manager': return
        self.clear(); top=ttk.Frame(self,padding=8); top.pack(fill='x'); ttk.Label(top,text='Manager Settings',font=('DejaVu Sans',22,'bold')).pack(side='left'); ttk.Button(top,text='Back to register',command=self.register_screen).pack(side='right')
        nb=ttk.Notebook(self); nb.pack(fill='both',expand=True,padx=10,pady=10)
        items=ttk.Frame(nb,padding=8); emps=ttk.Frame(nb,padding=8); sales=ttk.Frame(nb,padding=8); system=ttk.Frame(nb,padding=8)
        nb.add(items,text='Items'); nb.add(emps,text='Employees'); nb.add(sales,text='Sales'); nb.add(system,text='System')
        self.build_items_tab(items); self.build_employees_tab(emps); self.build_sales_tab(sales); self.build_system_tab(system)

    def build_items_tab(self,parent):
        tree=ttk.Treeview(parent,columns=('barcode','price','category','stock','active'),show='tree headings'); tree.pack(fill='both',expand=True)
        for c,t in [('#0','Name'),('barcode','Barcode'),('price','Price'),('category','Category'),('stock','Stock'),('active','Active')]: tree.heading(c,text=t)
        def load():
            tree.delete(*tree.get_children())
            for i in DB.items(): tree.insert('', 'end',iid=str(i['id']),text=i['name'],values=(i['barcode'] or '',money(i['price_cents']),i['category'],i['stock_qty'],'Yes' if i['active'] else 'No'))
        def edit(new=False):
            iid=None if new or not tree.selection() else int(tree.selection()[0]); row=DB.item_by_id(iid) if iid else None
            win=tk.Toplevel(self); win.title('Item'); vals={}
            fields=[('Name','name',row['name'] if row else ''),('Barcode','barcode',row['barcode'] if row and row['barcode'] else ''),('Price','price',f"{row['price_cents']/100:.2f}" if row else '0.00'),('Category','category',row['category'] if row else 'General'),('Stock quantity','stock',str(row['stock_qty']) if row else '0'),('Low-stock warning','low',str(row['low_stock']) if row else '0')]
            for r,(lab,key,val) in enumerate(fields): ttk.Label(win,text=lab).grid(row=r,column=0,sticky='w',padx=8,pady=5); v=tk.StringVar(value=val); vals[key]=v; ttk.Entry(win,textvariable=v).grid(row=r,column=1,padx=8,pady=5)
            active=tk.BooleanVar(value=bool(row['active']) if row else True); ttk.Checkbutton(win,text='Active',variable=active).grid(row=len(fields),columnspan=2)
            def save():
                try: DB.save_item(iid,vals['name'].get().strip(),vals['barcode'].get(),cents(vals['price'].get()),vals['category'].get().strip() or 'General',int(vals['stock'].get()),int(vals['low'].get()),active.get()); win.destroy(); load()
                except Exception as e: messagebox.showerror('Cannot save',str(e),parent=win)
            ttk.Button(win,text='Save',command=save).grid(row=len(fields)+1,column=0,columnspan=2,sticky='ew',padx=8,pady=8)
        bar=ttk.Frame(parent); bar.pack(fill='x'); ttk.Button(bar,text='Add item',command=lambda:edit(True)).pack(side='left'); ttk.Button(bar,text='Edit selected',command=edit).pack(side='left'); ttk.Button(bar,text='Delete selected',command=lambda:[DB.delete_item(int(x)) for x in tree.selection()] or load()).pack(side='left'); load()

    def build_employees_tab(self,parent):
        tree=ttk.Treeview(parent,columns=('role','active'),show='tree headings'); tree.pack(fill='both',expand=True); tree.heading('#0',text='Name'); tree.heading('role',text='Role'); tree.heading('active',text='Active')
        def load():
            tree.delete(*tree.get_children())
            for e in DB.employees(): tree.insert('', 'end',iid=str(e['id']),text=e['name'],values=(e['role'],'Yes' if e['active'] else 'No'))
        def edit(new=False):
            eid=None if new or not tree.selection() else int(tree.selection()[0]); row=DB.employee_by_id(eid) if eid else None
            win=tk.Toplevel(self); name=tk.StringVar(value=row['name'] if row else ''); role=tk.StringVar(value=row['role'] if row else 'cashier'); pin=tk.StringVar(); active=tk.BooleanVar(value=bool(row['active']) if row else True)
            for r,(lab,var,show) in enumerate([('Name',name,''),('New PIN (optional when editing)',pin,'•')]): ttk.Label(win,text=lab).grid(row=r,column=0,padx=8,pady=6); ttk.Entry(win,textvariable=var,show=show).grid(row=r,column=1,padx=8,pady=6)
            ttk.Label(win,text='Role').grid(row=2,column=0); ttk.Combobox(win,textvariable=role,values=('cashier','manager'),state='readonly').grid(row=2,column=1); ttk.Checkbutton(win,text='Active',variable=active).grid(row=3,columnspan=2)
            def save():
                try:
                    ph=hash_pin(pin.get()) if pin.get() else None
                    if not eid and not ph: raise ValueError('A PIN is required for a new employee')
                    if eid: DB.update_employee(eid,name.get().strip(),role.get(),active.get(),ph)
                    else: DB.add_employee(name.get().strip(),ph,role.get())
                    win.destroy(); load()
                except Exception as e: messagebox.showerror('Cannot save',str(e),parent=win)
            ttk.Button(win,text='Save',command=save).grid(row=4,columnspan=2,sticky='ew',padx=8,pady=8)
        bar=ttk.Frame(parent); bar.pack(fill='x'); ttk.Button(bar,text='Add employee',command=lambda:edit(True)).pack(side='left'); ttk.Button(bar,text='Edit selected',command=edit).pack(side='left'); ttk.Button(bar,text='Delete selected',command=lambda:[DB.delete_employee(int(x)) for x in tree.selection()] or load()).pack(side='left'); load()

    def build_sales_tab(self,parent):
        tree=ttk.Treeview(parent,columns=('employee','total','cash','change','date'),show='tree headings'); tree.pack(fill='both',expand=True)
        tree.heading('#0',text='Sale');
        for c,t in [('employee','Employee'),('total','Total'),('cash','Cash'),('change','Change'),('date','Date')]: tree.heading(c,text=t)
        for s in DB.sales(): tree.insert('', 'end',text=f"#{s['id']}",values=(s['employee_name'],money(s['total_cents']),money(s['cash_cents']),money(s['change_cents']),s['created_at']))

    def build_system_tab(self,parent):
        ttk.Label(parent,text='POSOS contains no tax calculation. Item prices are final prices.',font=('DejaVu Sans',14,'bold')).pack(anchor='w',pady=8)
        ttk.Button(parent,text='Back up database',command=self.backup_database).pack(anchor='w',pady=5)
        ttk.Button(parent,text='Exit POSOS',command=self.destroy).pack(anchor='w',pady=5)
    def backup_database(self):
        dest=DATA_DIR/'backups'; dest.mkdir(parents=True,exist_ok=True); name=dest/'posos-manual-backup.db'; shutil.copy2(DB.path,name); messagebox.showinfo('Backup',f'Backup saved to {name}')
    def manager_exit(self):
        if self.current_user and self.current_user['role']=='manager': self.destroy()


def main(): POSOS().mainloop()
